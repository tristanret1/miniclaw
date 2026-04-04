"""Message sanitization/transformation middleware for LLM providers."""

from bot.logger import get_logger
from bot.message import Message

log = get_logger("transform")


def sanitize_for_anthropic(messages: list[Message]) -> list[Message]:
    """Sanitize message history for the Anthropic API.

    Ensures:
    1. Every assistant message with tool_use blocks is immediately
       followed by a user message with matching tool_result blocks.
    2. Every tool_result references a tool_use_id from the previous
       assistant message.
    3. History starts with a user message.
    4. Roles alternate (user, assistant, user, assistant, ...).
    """
    if not messages:
        return messages

    sanitized: list[Message] = []
    i = 0
    while i < len(messages):
        msg = messages[i]

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
                if i + 1 < len(messages):
                    next_msg = messages[i + 1]
                    next_content = next_msg.get("content", [])

                    if (
                        next_msg.get("role") == "user"
                        and isinstance(next_content, list)
                    ):
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
                if i < len(messages):
                    nc = messages[i].get("content", [])
                    if (
                        isinstance(nc, list)
                        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in nc)
                    ):
                        log.warning("dropping orphan tool_result at index %d", i)
                        i += 1
                continue

        # Drop user messages that contain tool_result without matching tool_use
        if msg.get("role") == "user":
            content = msg.get("content", [])
            if isinstance(content, list):
                result_ids = {
                    b.get("tool_use_id") for b in content
                    if isinstance(b, dict) and b.get("type") == "tool_result"
                }
                if result_ids:
                    # Must have preceding assistant with matching tool_use IDs
                    prev_tool_use_ids: set[str] = set()
                    if sanitized and sanitized[-1].get("role") == "assistant":
                        prev_content = sanitized[-1].get("content", [])
                        if isinstance(prev_content, list):
                            prev_tool_use_ids = {
                                b["id"] for b in prev_content
                                if isinstance(b, dict)
                                and b.get("type") == "tool_use"
                                and "id" in b
                            }
                    if not result_ids <= prev_tool_use_ids:
                        log.warning(
                            "dropping orphan tool_result user message at index %d "
                            "(result_ids=%s, prev_use_ids=%s)",
                            i, result_ids, prev_tool_use_ids,
                        )
                        i += 1
                        continue

        sanitized.append(msg)
        i += 1

    # Ensure history starts with a user message
    while sanitized and sanitized[0].get("role") != "user":
        sanitized.pop(0)

    # Ensure roles alternate: drop consecutive same-role messages
    deduped: list[Message] = []
    for msg in sanitized:
        if deduped and deduped[-1].get("role") == msg.get("role"):
            log.warning("dropping duplicate %s message to fix alternation", msg.get("role"))
            continue
        deduped.append(msg)

    return deduped


def sanitize_for_codex(messages: list[Message]) -> list[Message]:
    """Sanitize message history for the Codex Responses API.

    Codex is more lenient than Anthropic but still requires:
    1. Every function_call must have a matching function_call_output.
    2. History should not start with an assistant message.
    """
    if not messages:
        return messages

    sanitized: list[Message] = []
    i = 0
    while i < len(messages):
        msg = messages[i]

        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            has_tool_use = (
                isinstance(content, list)
                and any(b.get("type") == "tool_use" for b in content if isinstance(b, dict))
            )

            if has_tool_use:
                # Must have a following tool_result
                if i + 1 < len(messages):
                    next_msg = messages[i + 1]
                    next_content = next_msg.get("content", [])
                    if (
                        next_msg.get("role") == "user"
                        and isinstance(next_content, list)
                        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in next_content)
                    ):
                        sanitized.append(msg)
                        sanitized.append(next_msg)
                        i += 2
                        continue

                # Drop orphan tool_use
                log.warning("codex: dropping orphan tool_use at index %d", i)
                i += 1
                if i < len(messages):
                    nc = messages[i].get("content", [])
                    if isinstance(nc, list) and any(
                        isinstance(b, dict) and b.get("type") == "tool_result" for b in nc
                    ):
                        i += 1
                continue

        sanitized.append(msg)
        i += 1

    # Ensure history starts with a user message
    while sanitized and sanitized[0].get("role") != "user":
        sanitized.pop(0)

    return sanitized


def sanitize(messages: list[Message], provider_id: str) -> list[Message]:
    """Route to the appropriate sanitizer for the given provider."""
    transformers = {
        "anthropic": sanitize_for_anthropic,
        "codex": sanitize_for_codex,
        # GLM and MiniMax use OpenAI-compatible format — same constraints as Codex
        "glm": sanitize_for_codex,
        "minimax": sanitize_for_codex,
    }
    fn = transformers.get(provider_id, lambda m: m)
    return fn(messages)


def strip_tool_blocks(messages: list[Message]) -> list[Message]:
    """Aggressively strip all tool_use/tool_result blocks, keeping only text.

    - Messages with only tool blocks are dropped entirely.
    - Mixed messages keep their text blocks only.
    - Consecutive same-role messages after stripping are merged.
    - Result starts with a user message with alternating roles.
    """
    cleaned: list[Message] = []
    for msg in messages:
        log.debug("stripping tool blocks from message: %s", msg)
        content = msg.get("content", "")
        role = msg.get("role", "user")

        if isinstance(content, str):
            cleaned.append({"role": role, "content": content})
            continue

        if isinstance(content, list):
            text_blocks = [
                b for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if not text_blocks:
                continue
            # Flatten to plain string if single text block
            if len(text_blocks) == 1:
                cleaned.append({"role": role, "content": text_blocks[0]["text"]})
            else:
                cleaned.append({"role": role, "content": text_blocks})
            continue

        # Unknown content type — keep as-is
        cleaned.append({"role": role, "content": content})

    # Merge consecutive same-role messages
    merged: list[Message] = []
    for msg in cleaned:
        if merged and merged[-1].get("role") == msg.get("role"):
            prev = merged[-1]["content"]
            curr = msg["content"]
            # Merge as strings when both are strings
            if isinstance(prev, str) and isinstance(curr, str):
                merged[-1]["content"] = prev + "\n\n" + curr
            else:
                log.warning("dropping duplicate %s message during strip_tool_blocks", msg.get("role"))
        else:
            merged.append(dict(msg))

    # Ensure starts with user
    while merged and merged[0].get("role") != "user":
        merged.pop(0)

    return merged
