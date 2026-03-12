"""Claude API calls — streaming, multimodal, with session persistence."""

from collections.abc import AsyncGenerator

import httpx
from bot.config import CLAUDE_MODEL, MAX_HISTORY, SYSTEM_PROMPT, TOOLS_ENABLED
from bot.logger import get_logger
from bot.memory import should_flush, get_flush_prompt
from bot.oauth import load_credentials, refresh_token
from bot.sessions import append_message, load_history
from bot.tools import ALL_TOOLS, handle_tool_call

log = get_logger("claude")

MESSAGES_URL = "https://api.anthropic.com/v1/messages"

# In-memory session cache (loaded from DB on first access)
_sessions: dict[str, list[dict]] = {}

# Track which sessions have been flushed
_flushed: set[str] = set()

MAX_TOOL_ROUNDS = 20


def _get_access_token() -> str:
    creds = load_credentials()
    if not creds:
        raise RuntimeError("Not authenticated. Run: python setup.py")
    return creds["access_token"]


def _build_request_body(messages: list[dict], stream: bool = False) -> dict:
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 4096,
        "system": SYSTEM_PROMPT,
        "messages": messages,
        "stream": stream,
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


# ── Non-streaming call (used by tool loop + auto-flush) ──────────────────────

def _call_claude(messages: list[dict]) -> dict:
    """Send messages to Claude and return the full response JSON."""
    token = _get_access_token()
    body = _build_request_body(messages, stream=False)

    resp = httpx.post(MESSAGES_URL, json=body, headers=_build_headers(token), timeout=120)

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


# ── Streaming call ────────────────────────────────────────────────────────────

async def _stream_claude(messages: list[dict]) -> AsyncGenerator[dict, None]:
    """Stream SSE events from Claude. Yields parsed event dicts."""
    token = _get_access_token()
    body = _build_request_body(messages, stream=True)

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", MESSAGES_URL, json=body, headers=_build_headers(token)
        ) as resp:
            if resp.status_code == 401:
                # Token refresh not supported in stream mode; fall back
                raise RuntimeError("Auth expired during stream")
            if resp.status_code != 200:
                text = await resp.aread()
                raise RuntimeError(f"Claude API error ({resp.status_code}): {text.decode()}")

            import json
            event_type = None
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: ") and event_type:
                    data = json.loads(line[6:])
                    data["_event"] = event_type
                    yield data
                    event_type = None


def _extract_text(content_blocks: list[dict]) -> str:
    return "\n".join(block["text"] for block in content_blocks if block["type"] == "text")


# ── Multimodal content builder ────────────────────────────────────────────────

def build_user_content(text: str, image_urls: list[str] | None = None) -> str | list[dict]:
    """Build user message content, optionally with images."""
    if not image_urls:
        return text

    blocks: list[dict] = []
    for url in image_urls:
        blocks.append({
            "type": "image",
            "source": {"type": "url", "url": url},
        })
    if text:
        blocks.append({"type": "text", "text": text})
    return blocks


# ── Session management ────────────────────────────────────────────────────────

def _get_history(session_key: str) -> list[dict]:
    """Get session history, loading from DB on first access."""
    if session_key not in _sessions:
        _sessions[session_key] = load_history(session_key, MAX_HISTORY * 2)
    return _sessions[session_key]


# ── Main entry: streaming reply ───────────────────────────────────────────────

async def get_reply_stream(
    session_key: str,
    user_content: str | list[dict],
) -> AsyncGenerator[str, None]:
    """Stream reply chunks. Yields text deltas as they arrive.

    Falls back to non-streaming for tool-use rounds, then streams the final reply.
    """
    history = _get_history(session_key)
    history.append({"role": "user", "content": user_content})
    append_message(session_key, "user", user_content)

    if len(history) > MAX_HISTORY * 2:
        history[:] = history[-(MAX_HISTORY * 2):]

    # Auto-flush check
    if session_key not in _flushed and should_flush(history):
        log.info("auto-flush triggered for session %s", session_key)
        _flushed.add(session_key)
        await _run_flush(session_key, history)

    # Tool-use loop (non-streaming, since we need full response to process tools)
    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        # Try streaming first — if no tool use, we stream directly to Discord
        collected_text = []
        collected_content = []
        stop_reason = None
        current_block = None

        try:
            async for event in _stream_claude(history):
                etype = event.get("_event")

                if etype == "content_block_start":
                    current_block = event.get("content_block", {})
                    if current_block.get("type") == "text":
                        current_block = {"type": "text", "text": ""}
                    collected_content.append(current_block)

                elif etype == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        chunk = delta["text"]
                        collected_text.append(chunk)
                        if current_block and current_block.get("type") == "text":
                            current_block["text"] += chunk
                        yield chunk
                    elif delta.get("type") == "input_json_delta":
                        # Tool input streaming — accumulate but don't yield
                        if current_block and "partial_json" not in current_block:
                            current_block["partial_json"] = ""
                        if current_block:
                            current_block["partial_json"] = current_block.get("partial_json", "") + delta.get("partial_json", "")

                elif etype == "content_block_stop":
                    # Finalize tool_use block input from accumulated JSON
                    if current_block and current_block.get("type") == "tool_use" and "partial_json" in current_block:
                        import json
                        try:
                            current_block["input"] = json.loads(current_block.pop("partial_json"))
                        except json.JSONDecodeError:
                            current_block["input"] = {}

                elif etype == "message_delta":
                    stop_reason = event.get("delta", {}).get("stop_reason")

        except RuntimeError as e:
            if "Auth expired" in str(e):
                # Fallback: refresh and use non-streaming
                response = _call_claude(history)
                collected_content = response.get("content", [])
                stop_reason = response.get("stop_reason")
                text = _extract_text(collected_content)
                yield text
            else:
                raise

        # Save assistant response
        history.append({"role": "assistant", "content": collected_content})
        append_message(session_key, "assistant", collected_content)

        if stop_reason != "tool_use":
            return

        # Process tool calls (non-streaming portion)
        tool_calls = [b for b in collected_content if b.get("type") == "tool_use"]
        log.info("tool round %d: %d call(s) — %s", round_num, len(tool_calls),
                 ", ".join(f"{b['name']}({b.get('input', {})})" for b in tool_calls))

        tool_results = []
        for block in tool_calls:
            try:
                result = await handle_tool_call(block["name"], block.get("input", {}))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result,
                })
            except Exception as e:
                log.error("tool call failed: %s → %s", block["name"], e)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": f"Error: {e}",
                    "is_error": True,
                })

        if not tool_results:
            yield "[Error: Tool execution failed]"
            return

        history.append({"role": "user", "content": tool_results})
        append_message(session_key, "user", tool_results)

    yield "[Stopped: too many tool calls]"


# ── Legacy non-streaming entry (for auto-reply, flush, etc.) ──────────────────

async def get_reply(session_key: str, user_message: str) -> str:
    """Non-streaming reply. Collects all chunks from stream."""
    chunks = []
    async for chunk in get_reply_stream(session_key, user_message):
        chunks.append(chunk)
    return "".join(chunks)


async def _run_flush(session_key: str, history: list[dict]) -> None:
    """Silent agentic turn: save conversation highlights to memory."""
    flush_history = history + [{"role": "user", "content": get_flush_prompt()}]

    try:
        for _ in range(5):
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
