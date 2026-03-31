"""Stream processor — tool loop, content accumulation, auto-flush."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from bot.config import get_config, get_system_prompt
from bot.constants import MAX_TOOL_ROUNDS
from bot.logger import get_logger
from bot.storage.memory import get_flush_prompt
from bot.message import Content, extract_text
from bot.provider.base import BaseProvider
from bot.provider.transform import sanitize, strip_tool_blocks
from bot.storage.session import SessionManager
from bot.tools import ALL_TOOLS, handle_tool_call

log = get_logger("processor")

# ── 24 Solar Terms (节气) ────────────────────────────────────────────────────
# Approximate dates using the Shouxi formula. Each solar term falls around a
# fixed date each year with ±1 day variance. We use a lookup of (month, day)
# pairs computed from the average tropical year.

_SOLAR_TERMS = [
    "小寒", "大寒", "立春", "雨水", "惊蛰", "春分",
    "清明", "谷雨", "立夏", "小满", "芒种", "夏至",
    "小暑", "大暑", "立秋", "处暑", "白露", "秋分",
    "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
]

# Century coefficients for 21st century (2000-2099)
_TERM_C = [
    5.4055, 20.12, 3.87, 18.73, 5.63, 20.646,
    4.81, 20.1, 5.52, 21.04, 5.678, 21.37,
    7.108, 22.83, 7.5, 23.13, 7.646, 23.042,
    8.318, 23.438, 7.438, 22.36, 7.18, 21.94,
]


def _get_solar_term(year: int, month: int, day: int) -> str | None:
    """Return the solar term name if today is a solar term day, else None."""
    import math

    # Each month has ~2 solar terms. Map month to term indices.
    # Term 0 (小寒) is in month 1, term 1 (大寒) is in month 1, etc.
    for i in range(24):
        term_month = (i // 2) + 1  # 1-indexed month
        if term_month != month:
            continue

        y = year % 100
        c = _TERM_C[i]
        # Shouxi formula: day = [Y*D + C] - [Y/4]  (D=0.2422)
        term_day = int(y * 0.2422 + c) - int(y / 4)

        # Known corrections for specific years
        if i == 0 and year == 2019:  # 小寒 2019
            term_day -= 1
        elif i == 2 and year == 2026:  # 立春 2026
            term_day += 1

        if term_day == day:
            return _SOLAR_TERMS[i]

    return None


class StreamProcessor:
    """Process LLM streaming responses: tool loop, content accumulation, auto-flush."""

    def __init__(self, provider: BaseProvider, session: SessionManager, session_key: str,
                 system_prompt: str | None = None, memory_dir=None, agent_name: str = "default"):
        self.provider = provider
        self.session = session
        self.session_key = session_key
        self._system_prompt = self._build_system_prompt(system_prompt or get_system_prompt())
        self._memory_dir = memory_dir
        self._agent_name = agent_name

    @staticmethod
    def _build_system_prompt(base: str) -> str:
        """Append real-time context (current time + timezone + lunar date) to system prompt."""
        now = datetime.now().astimezone()
        tz_name = now.tzname() or "UTC"
        time_str = now.strftime(f"%Y-%m-%d %H:%M %A ({tz_name})")

        # Chinese lunar calendar + 天干地支
        lunar_str = ""
        try:
            from lunardate import LunarDate
            ld = LunarDate.fromSolarDate(now.year, now.month, now.day)
            leap = "闰" if ld.isLeapMonth else ""

            天干 = "甲乙丙丁戊己庚辛壬癸"
            地支 = "子丑寅卯辰巳午未申酉戌亥"
            gz_year = 天干[(ld.year - 4) % 10] + 地支[(ld.year - 4) % 12]
            gz_month = 天干[(ld.year * 12 + ld.month + 3) % 10] + 地支[(ld.month + 1) % 12]
            # 日干支：以已知基准点推算（2000-01-01 = 甲子日近似偏移）
            from datetime import date
            day_offset = (date(now.year, now.month, now.day) - date(2000, 1, 7)).days
            gz_day = 天干[day_offset % 10] + 地支[day_offset % 12]

            # 24节气
            solar_term = _get_solar_term(now.year, now.month, now.day)
            term_str = f" · {solar_term}" if solar_term else ""

            lunar_str = f" | 农历{leap}{ld.month}月{ld.day}日 | {gz_year}年{gz_month}月{gz_day}日{term_str}"
        except ImportError:
            pass

        return f"{base}\n\nCurrent time: {time_str}{lunar_str}"

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
        tools = ALL_TOOLS if get_config().llm.tools_enabled else None

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
             
                    sanitized = sanitize(history, get_config().llm.provider)
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
        flush_history = sanitize(history, get_config().llm.provider) + [
            {"role": "user", "content": get_flush_prompt()}
        ]
        tools = ALL_TOOLS if get_config().llm.tools_enabled else None

        try:
            for _ in range(5):
                try:
                    response = await self.provider.call(
                        flush_history, self._system_prompt, tools=tools
                    )
                except RuntimeError as e:
                    if "400" in str(e) or "tool_use" in str(e) or "tool_result" in str(e):
                        flush_history = sanitize(flush_history, get_config().llm.provider)
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
