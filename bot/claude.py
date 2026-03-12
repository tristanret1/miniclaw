"""Claude API calls using OAuth Bearer token (not x-api-key)."""

import httpx
from bot.config import CLAUDE_MODEL, MAX_HISTORY, SYSTEM_PROMPT, TOOLS_ENABLED
from bot.logger import get_logger
from bot.memory import should_flush, get_flush_prompt
from bot.oauth import load_credentials, refresh_token
from bot.tools import ALL_TOOLS, handle_tool_call

log = get_logger("claude")

MESSAGES_URL = "https://api.anthropic.com/v1/messages"

# Per-conversation message history
_sessions: dict[str, list[dict]] = {}

# Track which sessions have been flushed (to avoid flushing twice)
_flushed: set[str] = set()

# Max tool-use rounds per single user message to prevent runaway loops
MAX_TOOL_ROUNDS = 20


def _get_access_token() -> str:
    creds = load_credentials()
    if not creds:
        raise RuntimeError("Not authenticated. Run: python setup.py")
    return creds["access_token"]


def _build_request_body(messages: list[dict]) -> dict:
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT,
        "messages": messages,
    }
    if TOOLS_ENABLED:
        body["tools"] = ALL_TOOLS
    return body


def _build_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
    }


def _call_claude(messages: list[dict]) -> dict:
    """Send messages to Claude and return the full response JSON."""
    token = _get_access_token()
    body = _build_request_body(messages)

    resp = httpx.post(MESSAGES_URL, json=body, headers=_build_headers(token), timeout=120)

    # Token expired → refresh and retry once
    if resp.status_code == 401:
        creds = load_credentials()
        if creds and creds.get("refresh_token"):
            new_creds = refresh_token(creds)
            resp = httpx.post(
                MESSAGES_URL, json=body, headers=_build_headers(new_creds["access_token"]), timeout=120
            )

    if resp.status_code != 200:
        raise RuntimeError(f"Claude API error ({resp.status_code}): {resp.text}")

    return resp.json()


def _extract_text(content_blocks: list[dict]) -> str:
    """Extract all text blocks from a Claude response."""
    return "\n".join(block["text"] for block in content_blocks if block["type"] == "text")


async def get_reply(session_key: str, user_message: str) -> str:
    history = _sessions.setdefault(session_key, [])
    history.append({"role": "user", "content": user_message})

    if len(history) > MAX_HISTORY * 2:
        history[:] = history[-(MAX_HISTORY * 2):]

    # Auto-flush: silently ask Claude to save important context before truncation
    if session_key not in _flushed and should_flush(history):
        log.info("auto-flush triggered for session %s", session_key)
        _flushed.add(session_key)
        await _run_flush(session_key, history)

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        response = _call_claude(history)
        stop_reason = response.get("stop_reason")
        content = response.get("content", [])

        # Append the full assistant response (text + tool_use blocks)
        history.append({"role": "assistant", "content": content})

        if stop_reason != "tool_use":
            reply = _extract_text(content)
            return reply

        # Process tool calls and collect results
        tool_calls = [b for b in content if b["type"] == "tool_use"]
        log.info("tool round %d: %d call(s) — %s", round_num, len(tool_calls),
                 ", ".join(f"{b['name']}({b['input']})" for b in tool_calls))

        tool_results = []
        for block in tool_calls:
            try:
                result = await handle_tool_call(block["name"], block["input"])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result,
                })
            except Exception as e:
                log.error("tool call failed: %s(%s) → %s", block["name"], block["input"], e)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": f"Error executing tool: {e}",
                    "is_error": True,
                })

        # Ensure we have at least one tool result before sending back to Claude
        if not tool_results:
            log.error("No tool results generated for %d tool calls", len(tool_calls))
            return "[Error: Tool execution failed]"

        # Feed tool results back to Claude
        history.append({"role": "user", "content": tool_results})

    log.warning("tool loop hit max rounds (%d) for session %s", MAX_TOOL_ROUNDS, session_key)
    return "[Stopped: too many tool calls]"


async def _run_flush(session_key: str, history: list[dict]) -> None:
    """Silent agentic turn: ask Claude to save conversation highlights to memory."""
    flush_history = history + [{"role": "user", "content": get_flush_prompt()}]

    try:
        for _ in range(5):  # up to 5 tool rounds for flushing
            response = _call_claude(flush_history)
            content = response.get("content", [])
            flush_history.append({"role": "assistant", "content": content})

            if response.get("stop_reason") != "tool_use":
                break

            tool_results = []
            for block in content:
                if block["type"] == "tool_use":
                    result = await handle_tool_call(block["name"], block["input"])
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": result,
                    })

            flush_history.append({"role": "user", "content": tool_results})

        log.info("auto-flush completed for session %s", session_key)
    except Exception as e:
        log.error("auto-flush failed for session %s: %s", session_key, e)
