"""Claude API calls — streaming, multimodal, with session persistence."""

import json
from collections.abc import AsyncGenerator

import httpx
from bot.config import (
    CLAUDE_MODEL,
    MAX_HISTORY,
    SYSTEM_PROMPT,
    TOOLS_ENABLED,
    HISTORY_CHAR_BUDGET,
)
from bot.logger import get_logger
from bot.memory import should_flush, get_flush_prompt, FLUSH_THRESHOLD_CHARS
from bot.oauth import load_credentials, refresh_token
from bot.sessions import append_message, load_history
from bot.tools import ALL_TOOLS, handle_tool_call

log = get_logger("claude")

MESSAGES_URL = "https://api.anthropic.com/v1/messages"

# In-memory session cache (loaded from DB on first access)
_sessions: dict[str, list[dict]] = {}

# Track which sessions have been flushed
_flushed: set[str] = set()
# Track last flush size per session to allow periodic flushes
_last_flush_size: dict[str, int] = {}

# Shared async HTTP client for connection pooling
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120, connect=10),
            http2=True,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _http_client

MAX_TOOL_ROUNDS = 200


def _get_access_token() -> str:
    creds = load_credentials()
    if not creds:
        raise RuntimeError("Not authenticated. Run: python setup.py")
    return creds["access_token"]


def _build_request_body(
    messages: list[dict],
    stream: bool = False,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
) -> dict:
    body = {
        "model": model or CLAUDE_MODEL,
        "max_tokens": 16384,
        "system": system_prompt or SYSTEM_PROMPT,
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

async def _call_claude(
    messages: list[dict],
    *,
    system_prompt: str | None = None,
    model: str | None = None,
) -> dict:
    """Send messages to Claude and return the full response JSON (async)."""
    token = _get_access_token()
    body = _build_request_body(messages, stream=False, system_prompt=system_prompt, model=model)
    client = _get_http_client()

    resp = await client.post(MESSAGES_URL, json=body, headers=_build_headers(token))

    if resp.status_code == 401:
        creds = load_credentials()
        if creds and creds.get("refresh_token"):
            new_creds = refresh_token(creds)
            resp = await client.post(
                MESSAGES_URL, json=body, headers=_build_headers(new_creds["access_token"])
            )

    if resp.status_code != 200:
        raise RuntimeError(f"Claude API error ({resp.status_code}): {resp.text}")

    return resp.json()


# ── Streaming call ────────────────────────────────────────────────────────────

async def _stream_claude(
    messages: list[dict],
    *,
    system_prompt: str | None = None,
    model: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream SSE events from Claude. Yields parsed event dicts."""
    token = _get_access_token()
    body = _build_request_body(messages, stream=True, system_prompt=system_prompt, model=model)
    client = _get_http_client()

    async with client.stream(
        "POST", MESSAGES_URL, json=body, headers=_build_headers(token)
    ) as resp:
        if resp.status_code == 401:
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

def _to_blocks(content: str | list[dict]) -> list[dict]:
    if isinstance(content, list):
        return content
    return [{"type": "text", "text": str(content)}]


def _merge_same_role(prev: dict, cur: dict) -> dict:
    """Merge two messages with the same role into one.

    - If content is string, concatenate with blank line.
    - If lists, extend in order.
    - If mixed, convert string to text block and extend.
    """
    if prev.get("role") != cur.get("role"):
        return cur
    pc, cc = prev.get("content"), cur.get("content")
    # Normalize to blocks
    p_blocks = _to_blocks(pc)
    c_blocks = _to_blocks(cc)
    merged = {"role": prev.get("role"), "content": list(p_blocks) + list(c_blocks)}
    return merged


def _sanitize_history(history: list[dict]) -> list[dict]:
    """Remove incomplete tool_use/tool_result pairs from history.

    Claude API requires:
    1. Every assistant message with tool_use blocks must be immediately
       followed by a user message with matching tool_result blocks.
    2. Every tool_result must reference a tool_use_id from the previous
       assistant message.
    3. History must start with a user message.
    4. Roles must alternate (user, assistant, user, assistant, ...).
    """
    if not history:
        return history

    sanitized = []
    i = 0
    while i < len(history):
        msg = history[i]

        # Check if this assistant message contains tool_use blocks
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            has_tool_use = (
                isinstance(content, list)
                and any(b.get("type") == "tool_use" for b in content if isinstance(b, dict))
            )

            if has_tool_use:
                # Collect tool_use IDs from this assistant message
                tool_use_ids = {
                    b["id"] for b in content
                    if isinstance(b, dict) and b.get("type") == "tool_use" and "id" in b
                }

                # Must have a following user message with matching tool_results
                if i + 1 < len(history):
                    next_msg = history[i + 1]
                    next_content = next_msg.get("content", [])

                    if (
                        next_msg.get("role") == "user"
                        and isinstance(next_content, list)
                    ):
                        # Check all tool_result IDs match a tool_use ID
                        result_ids = {
                            b.get("tool_use_id") for b in next_content
                            if isinstance(b, dict) and b.get("type") == "tool_result"
                        }

                        if result_ids and result_ids <= tool_use_ids:
                            sanitized.append(msg)
                            sanitized.append(next_msg)
                            i += 2
                            continue

                # Incomplete or mismatched pair — drop both
                log.warning("dropping orphan tool_use/tool_result at index %d", i)
                i += 1
                # Also skip the next message if it's an orphan tool_result
                if i < len(history):
                    nc = history[i].get("content", [])
                    if (
                        isinstance(nc, list)
                        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in nc)
                    ):
                        log.warning("dropping orphan tool_result at index %d", i)
                        i += 1
                continue

        # Drop user messages that contain tool_result without a preceding tool_use
        if msg.get("role") == "user":
            content = msg.get("content", [])
            if (
                isinstance(content, list)
                and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
            ):
                # Check if previous sanitized message is a matching assistant tool_use
                if not sanitized or sanitized[-1].get("role") != "assistant":
                    log.warning("dropping orphan tool_result user message at index %d", i)
                    i += 1
                    continue

        sanitized.append(msg)
        i += 1

    # Ensure history starts with a user message (Claude API requirement)
    while sanitized and sanitized[0].get("role") != "user":
        sanitized.pop(0)

    # Ensure roles alternate by merging consecutive same-role messages instead of dropping
    merged: list[dict] = []
    for msg in sanitized:
        if merged and merged[-1].get("role") == msg.get("role"):
            merged[-1] = _merge_same_role(merged[-1], msg)
        else:
            merged.append(msg)

    return merged


def _get_history(session_key: str) -> list[dict]:
    """Get session history; lazily load from DB on first access."""
    if session_key not in _sessions:
        try:
            # Load a generous slice from DB; further windowing happens per request
            db_hist = load_history(session_key, MAX_HISTORY * 2)
            _sessions[session_key] = _sanitize_history(db_hist)
            log.info("session %s initialized from DB with %d messages", session_key, len(_sessions[session_key]))
        except Exception as e:
            log.warning("failed to load history for %s: %s", session_key, e)
            _sessions[session_key] = []
    return _sessions[session_key]


def _total_chars(history: list[dict]) -> int:
    try:
        return sum(len(json.dumps(m.get("content", ""), ensure_ascii=False)) for m in history)
    except Exception:
        return 0


def _pair_aware_window(history: list[dict], budget_chars: int, keep_last_pairs: int = 6) -> list[dict]:
    """Build a rolling window under character budget, preserving pairs.

    - Walk from the end, collecting messages until budget is reached.
    - Keep at least keep_last_pairs full user↔assistant exchanges if possible.
    - Preserve assistant tool_use followed by user tool_result.
    - Merge consecutive same-role messages on the fly.
    """
    if not history:
        return history

    hist = _sanitize_history(history)
    out: list[dict] = []
    used = 0
    pairs_kept = 0

    i = len(hist) - 1
    while i >= 0:
        msg = hist[i]

        # Prepend to output (we're walking backwards)
        if out and out[0].get("role") == msg.get("role"):
            out[0] = _merge_same_role(msg, out[0])
        else:
            out.insert(0, msg)

        used = _total_chars(out)
        if used >= budget_chars and pairs_kept >= keep_last_pairs:
            # Remove earliest messages until within budget
            while out and _total_chars(out) > budget_chars:
                out.pop(0)
            break

        # Count full pairs when we just added an assistant message and previous is user
        if len(out) >= 2 and out[-2].get("role") == "user" and out[-1].get("role") == "assistant":
            pairs_kept += 1

        # Preserve tool_use/tool_result adjacency: if current is assistant tool_use,
        # ensure next user tool_result comes along (when walking backwards, that's i+1)
        # Already handled by sanitize, which ensures valid pairs; nothing extra here.

        i -= 1

    return out


# ── Main entry: streaming reply ───────────────────────────────────────────────

async def get_reply_stream(
    session_key: str,
    user_content: str | list[dict],
    *,
    system_prompt_override: str | None = None,
    model_override: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream reply chunks. Yields text deltas as they arrive.

    Falls back to non-streaming for tool-use rounds, then streams the final reply.
    """
    history = _get_history(session_key)
    history.append({"role": "user", "content": user_content})
    append_message(session_key, "user", user_content)

    # Build a pair-aware, budgeted window for the model call (recomputed each round)
    effective_history = _pair_aware_window(history, HISTORY_CHAR_BUDGET)

    # Auto-flush check — run in background so it doesn't block the reply
    # Auto-flush: allow repeated flushes when size grows substantially.
    # Skip when tools are disabled (flush depends on memory_save).
    if TOOLS_ENABLED:
        total = _total_chars(history)
        last = _last_flush_size.get(session_key, 0)
        # Trigger when crossing threshold and growth since last flush ≥ 40k chars
        if total >= FLUSH_THRESHOLD_CHARS and (total - last) >= 40_000:
            log.info("auto-flush triggered for session %s (background)", session_key)
            _last_flush_size[session_key] = total
            import asyncio
            asyncio.create_task(_run_flush(session_key, list(history)))

    # Tool-use loop (non-streaming, since we need full response to process tools)
    _consecutive_400s = 0
    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        # Try streaming first — if no tool use, we stream directly to Discord
        collected_text = []
        collected_content = []
        stop_reason = None
        current_block = None

        try:
            # Recompute window each round to include latest tool results, etc.
            effective_history = _pair_aware_window(history, HISTORY_CHAR_BUDGET)
            async for event in _stream_claude(
                effective_history,
                system_prompt=system_prompt_override,
                model=model_override,
            ):
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
                response = await _call_claude(
                    effective_history,
                    system_prompt=system_prompt_override,
                    model=model_override,
                )
                collected_content = response.get("content", [])
                stop_reason = response.get("stop_reason")
                text = _extract_text(collected_content)
                yield text
            elif "tool_use" in str(e) or "tool_result" in str(e) or "400" in str(e):
                _consecutive_400s += 1
                old_len = len(history)
                history[:] = _sanitize_history(history)
                log.warning(
                    "400 error (attempt %d): %s — sanitized history: %d → %d messages",
                    _consecutive_400s, str(e)[:200], old_len, len(history),
                )

                if not history:
                    yield "[Error: conversation history was corrupted and cleared. Please try again.]"
                    return

                # If sanitize didn't help, progressively trim oldest messages
                if len(history) == old_len and _consecutive_400s >= 2:
                    # Drop oldest 2 messages (preserve user/assistant pairing)
                    trim = min(2, len(history) - 1)
                    history[:] = history[trim:]
                    # Ensure still starts with user
                    while history and history[0].get("role") != "user":
                        history.pop(0)
                    log.warning("400 persisted — trimmed %d oldest messages, %d remaining", trim, len(history))

                if _consecutive_400s >= 5:
                    log.error("400 error after %d retries, giving up", _consecutive_400s)
                    yield "[Error: repeated API errors. Try starting a new conversation.]"
                    return

                continue
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

        # Execute tool calls concurrently for better performance
        async def _run_tool(block: dict) -> dict:
            try:
                result = await handle_tool_call(block["name"], block.get("input", {}))
                return {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result,
                }
            except Exception as e:
                log.error("tool call failed: %s → %s", block["name"], e)
                return {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": f"Error: {e}",
                    "is_error": True,
                }

        import asyncio as _aio
        tool_results = await _aio.gather(*[_run_tool(b) for b in tool_calls])

        if not tool_results:
            err_msg = "[Error: Tool execution failed]"
            err_content = [{"type": "text", "text": err_msg}]
            history.append({"role": "assistant", "content": err_content})
            append_message(session_key, "assistant", err_content)
            yield err_msg
            return

        history.append({"role": "user", "content": tool_results})
        append_message(session_key, "user", tool_results)

    # Tool loop exhausted — close with a synthetic assistant message so
    # history doesn't end with an orphan tool_result (which causes 400 on
    # the next conversation turn).
    stop_msg = "[Stopped: too many tool calls]"
    stop_content = [{"type": "text", "text": stop_msg}]
    history.append({"role": "assistant", "content": stop_content})
    append_message(session_key, "assistant", stop_content)
    yield stop_msg


# ── Legacy non-streaming entry (for auto-reply, flush, etc.) ──────────────────

async def get_reply(session_key: str, user_message: str) -> str:
    """Non-streaming reply. Collects all chunks from stream."""
    chunks = []
    async for chunk in get_reply_stream(session_key, user_message):
        chunks.append(chunk)
    return "".join(chunks)


# ── Isolated agent turn (for cron, background tasks) ─────────────────────────

async def run_isolated_turn(
    message: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    max_rounds: int = 10,
    timeout: float = 300,
) -> str:
    """Run a single isolated agent turn with full tool-use loop.

    Unlike get_reply(), this function:
    - Does NOT load or persist session history
    - Does NOT trigger auto-flush
    - Uses an ephemeral messages list (discarded after return)
    - Supports custom system_prompt and model overrides
    """
    import asyncio as _aio

    messages: list[dict] = [{"role": "user", "content": message}]

    async def _do_turn() -> str:
        for round_num in range(1, max_rounds + 1):
            body = _build_request_body(
                messages, stream=False,
                system_prompt=system_prompt, model=model,
            )
            token = _get_access_token()
            client = _get_http_client()

            resp = await client.post(MESSAGES_URL, json=body, headers=_build_headers(token))

            if resp.status_code == 401:
                creds = load_credentials()
                if creds and creds.get("refresh_token"):
                    new_creds = refresh_token(creds)
                    resp = await client.post(
                        MESSAGES_URL, json=body, headers=_build_headers(new_creds["access_token"])
                    )

            if resp.status_code != 200:
                raise RuntimeError(f"Claude API error ({resp.status_code}): {resp.text}")

            response = resp.json()
            content = response.get("content", [])
            messages.append({"role": "assistant", "content": content})

            if response.get("stop_reason") != "tool_use":
                return _extract_text(content)

            # Process tool calls
            tool_calls = [b for b in content if b.get("type") == "tool_use"]
            log.info("isolated turn round %d: %d tool call(s) — %s", round_num, len(tool_calls),
                     ", ".join(b["name"] for b in tool_calls))

            async def _run_tool(block: dict) -> dict:
                try:
                    result = await handle_tool_call(block["name"], block.get("input", {}))
                    return {"type": "tool_result", "tool_use_id": block["id"], "content": result}
                except Exception as e:
                    log.error("isolated tool call failed: %s → %s", block["name"], e)
                    return {"type": "tool_result", "tool_use_id": block["id"],
                            "content": f"Error: {e}", "is_error": True}

            tool_results = await _aio.gather(*[_run_tool(b) for b in tool_calls])
            messages.append({"role": "user", "content": list(tool_results)})

        return "[Stopped: too many tool calls]"

    try:
        return await _aio.wait_for(_do_turn(), timeout=timeout)
    except _aio.TimeoutError:
        log.warning("isolated turn timed out after %.0fs", timeout)
        return f"[Timed out after {timeout:.0f}s]"


async def _run_flush(session_key: str, history: list[dict]) -> None:
    """Silent agentic turn: save conversation highlights to memory."""
    flush_history = _sanitize_history(history) + [{"role": "user", "content": get_flush_prompt()}]

    try:
        for _ in range(5):
            try:
                response = await _call_claude(flush_history)
            except RuntimeError as e:
                if "400" in str(e) or "tool_use" in str(e) or "tool_result" in str(e):
                    flush_history = _sanitize_history(flush_history)
                    log.warning("flush: sanitized history after 400, retrying")
                    response = await _call_claude(flush_history)
                else:
                    raise

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
