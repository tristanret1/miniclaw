"""Stream processor — tool loop, content accumulation, auto-flush."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from bot.config import PROVIDER, SYSTEM_PROMPT, TOOLS_ENABLED
from bot.logger import get_logger
from bot.memory import get_flush_prompt
from bot.message import Content, extract_text
from bot.provider.base import BaseProvider
from bot.provider.transform import sanitize, strip_tool_blocks
from bot.session import SessionManager
from bot.tools import ALL_TOOLS, handle_tool_call

log = get_logger("processor")

MAX_TOOL_ROUNDS = 20


class StreamProcessor:
    """Process LLM streaming responses: tool loop, content accumulation, auto-flush."""

    def __init__(self, provider: BaseProvider, session: SessionManager, session_key: str,
                 system_prompt: str | None = None, memory_dir=None, agent_name: str = "default"):
        self.provider = provider
        self.session = session
        self.session_key = session_key
        self._system_prompt = self._build_system_prompt(system_prompt or SYSTEM_PROMPT)
        self._memory_dir = memory_dir
        self._agent_name = agent_name

    @staticmethod
    def _build_system_prompt(base: str) -> str:
        """Append real-time context (current time + timezone) to system prompt."""
        now = datetime.now().astimezone()
        tz_name = now.tzname() or "UTC"
        time_str = now.strftime(f"%Y-%m-%d %H:%M %A ({tz_name})")
        return f"{base}\n\nCurrent time: {time_str}"

    async def process(self, user_content: Content) -> AsyncIterator[str]:
        """Full processing flow: append user message, tool loop, yield text chunks."""
        await self.session.append(self.session_key, "user", user_content)
        await self.session.trim(self.session_key)

        # Auto-flush check — run in background
        if await self.session.should_flush(self.session_key):
            log.info("auto-flush triggered for session %s (background)", self.session_key)
            self.session.mark_flushed(self.session_key)
            history_copy = list(await self.session.get_history(self.session_key))
            asyncio.create_task(self._run_flush(history_copy))

        history = await self.session.get_history(self.session_key)
        tools = ALL_TOOLS if TOOLS_ENABLED else None

        for round_num in range(1, MAX_TOOL_ROUNDS + 1):
            collected_text: list[str] = []
            collected_content: list[dict] = []
            stop_reason = None
            current_block = None

            try:
                async for event in self.provider.stream(
                    history, self._system_prompt, tools=tools
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
                            if current_block and "partial_json" not in current_block:
                                current_block["partial_json"] = ""
                            if current_block:
                                current_block["partial_json"] = (
                                    current_block.get("partial_json", "")
                                    + delta.get("partial_json", "")
                                )

                    elif etype == "content_block_stop":
                        if (
                            current_block
                            and current_block.get("type") == "tool_use"
                            and "partial_json" in current_block
                        ):
                            try:
                                current_block["input"] = json.loads(
                                    current_block.pop("partial_json")
                                )
                            except json.JSONDecodeError:
                                current_block["input"] = {}

                    elif etype == "message_delta":
                        stop_reason = event.get("delta", {}).get("stop_reason")

            except RuntimeError as e:
                log.error("LLM call error on round %d: %s", round_num, e)
                if "Auth expired" in str(e):
                    response = await self.provider.call(
                        history, self._system_prompt, tools=tools
                    )
                    collected_content = response.get("content", [])
                    stop_reason = response.get("stop_reason")
                    text = extract_text(collected_content)
                    yield text
                elif "tool_use" in str(e) or "tool_result" in str(e) or "400" in str(e):
                    old_len = len(history)
             
                    sanitized = sanitize(history, PROVIDER)
                    if len(sanitized) == old_len:
                        # sanitize didn't help — aggressively strip all tool blocks
                        history[:] = strip_tool_blocks(history)
                        log.warning(
                                "400 tool mismatch — sanitize unchanged, stripped all tool blocks: %d -> %d messages",
                                old_len, len(history),
                        )
                    else:
                        history[:] = sanitized
                        log.warning(
                                "400 tool mismatch — sanitized history: %d -> %d messages, retrying",
                                old_len, len(history),
                        )
                    if not history:
                        yield "[Error: conversation history was corrupted and cleared. Please try again.]"
                        return
                    continue
                else:
                    raise

            # Save assistant response
            await self.session.append(self.session_key, "assistant", collected_content)

            if stop_reason != "tool_use":
                return

            # Process tool calls
            tool_blocks = [b for b in collected_content if b.get("type") == "tool_use"]
            log.info(
                "tool round %d: %d call(s) — %s",
                round_num,
                len(tool_blocks),
                ", ".join(f"{b['name']}({b.get('input', {})})" for b in tool_blocks),
            )

            tool_results = await self._handle_tool_calls(tool_blocks)

            if not tool_results:
                yield "[Error: Tool execution failed]"
                return

            await self.session.append(self.session_key, "user", tool_results)

        yield "[Stopped: too many tool calls]"

    async def _handle_tool_calls(self, tool_blocks: list[dict]) -> list[dict]:
        """Execute tool calls concurrently, return results."""

        async def _run_tool(block: dict) -> dict:
            try:
                result = await handle_tool_call(block["name"], block.get("input", {}),
                                               memory_dir=self._memory_dir,
                                               agent_name=self._agent_name)
                return {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result,
                }
            except Exception as e:
                log.error("tool call failed: %s -> %s", block["name"], e)
                return {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": f"Error: {e}",
                    "is_error": True,
                }

        return list(await asyncio.gather(*[_run_tool(b) for b in tool_blocks]))

    async def _run_flush(self, history: list[dict]) -> None:
        """Background auto-flush: save conversation highlights to memory."""
        flush_history = sanitize(history, PROVIDER) + [
            {"role": "user", "content": get_flush_prompt()}
        ]
        tools = ALL_TOOLS if TOOLS_ENABLED else None

        try:
            for _ in range(5):
                try:
                    response = await self.provider.call(
                        flush_history, self._system_prompt, tools=tools
                    )
                except RuntimeError as e:
                    if "400" in str(e) or "tool_use" in str(e) or "tool_result" in str(e):
                        flush_history = sanitize(flush_history, PROVIDER)
                        log.warning("flush: sanitized history after 400, retrying")
                        response = await self.provider.call(
                            flush_history, self._system_prompt, tools=tools
                        )
                    else:
                        raise

                content = response.get("content", [])
                flush_history.append({"role": "assistant", "content": content})

                if response.get("stop_reason") != "tool_use":
                    break

                tool_results = []
                for block in content:
                    if block["type"] == "tool_use":
                        result = await handle_tool_call(block["name"], block["input"],
                                                        memory_dir=self._memory_dir,
                                                        agent_name=self._agent_name)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": result,
                        })
                flush_history.append({"role": "user", "content": tool_results})

            log.info("auto-flush completed for session %s", self.session_key)
        except Exception as e:
            log.error("auto-flush failed for session %s: %s", self.session_key, e)
