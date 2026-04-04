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


# ── 历史记录压缩 ────────────────────────────────────────────────────────────
# 工具循环中 tool_result 会快速累积（每轮 3 个搜索 × 6 轮 = 18 条），
# 导致 input tokens 膨胀。当历史超过阈值时，将旧 tool_result 的 content
# 替换为简短占位符，只保留最近一轮的完整结果供 LLM 参考。

# 粗估 token 数的阈值（~10k tokens ≈ 40k chars，中文约 2 char/token）
_COMPACT_CHAR_THRESHOLD = 40_000


def _estimate_history_chars(history: list[dict]) -> int:
    """粗估历史记录的总字符数。"""
    total = 0
    for msg in history:
        c = msg.get("content")
        if isinstance(c, str):
            total += len(c)
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict):
                    # tool_result content / text block
                    total += len(str(block.get("content", "")))
                    total += len(str(block.get("text", "")))
                elif isinstance(block, str):
                    total += len(block)
    return total


def _compact_tool_results(history: list[dict]) -> None:
    """原地压缩历史中的旧 tool_result，超阈值时触发。

    策略：
    - 找到所有包含 tool_result 的 user 消息
    - 保留最后一条（最近一轮的结果），压缩其余所有
    - 每个 tool_result 的 content 替换为 "[已清理的工具结果]"
    - assistant 消息中的 tool_use block 保留（API 要求 tool_use/tool_result 配对）
    """
    if _estimate_history_chars(history) < _COMPACT_CHAR_THRESHOLD:
        return

    # 找出所有含 tool_result 的 user 消息的索引
    tool_msg_indices = []
    for i, msg in enumerate(history):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        ):
            tool_msg_indices.append(i)

    if len(tool_msg_indices) <= 1:
        # 只有一轮或没有 tool_result，不压缩
        return

    # 保留最后一条 tool_result 消息完整，压缩其余
    chars_before = _estimate_history_chars(history)
    for idx in tool_msg_indices[:-1]:
        content = history[idx]["content"]
        if not isinstance(content, list):
            continue
        compacted = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                compacted.append({
                    "type": "tool_result",
                    "tool_use_id": block.get("tool_use_id", ""),
                    "content": "[已清理的工具结果]",
                })
            else:
                compacted.append(block)
        history[idx] = {"role": "user", "content": compacted}

    chars_after = _estimate_history_chars(history)
    log.info(
        "compacted tool results: %d tool messages compressed, ~%dk → ~%dk chars",
        len(tool_msg_indices) - 1,
        chars_before // 1000,
        chars_after // 1000,
    )


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
            # 每轮 API 调用前检查历史大小，超过阈值时压缩旧的 tool_result
            _compact_tool_results(history)

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

            tool_results, tool_results_for_history = await self._handle_tool_calls(tool_blocks)

            if not tool_results:
                yield "[Error: Tool execution failed]"
                return

            # 将纯文本版本写入 DB（prompt cache 友好）
            await self.session.append(self.session_key, "user", tool_results_for_history)

            if tool_results != tool_results_for_history:
                # 内存中替换为完整版本（含截图），让当前工具循环的下一轮 API 调用能看到图片。
                # 重启后从 DB 加载时只会拿到纯文本版本 — 截图仅在当前工具循环内存活。
                history[-1] = {"role": "user", "content": tool_results}

        yield "[Stopped: too many tool calls]"

    async def _handle_tool_calls(self, tool_blocks: list[dict]) -> tuple[list[dict], list[dict]]:
        """并发执行工具调用，返回两个版本的结果。

        Returns:
            (full_results, history_results) 元组：
            - full_results:    完整结果（含截图 image block），用于当前 API 调用
            - history_results: 纯文本结果（截图替换为占位符），用于持久化到 session DB

        为什么要分两个版本？
        截图的 base64 每次像素不同，存入历史会导致 Claude prompt cache 失效，
        整段历史每轮都要重新计费。纯文本前缀稳定，cache 命中率高。
        当前工具循环内 LLM 仍然能看到截图（通过内存中的 full_results），
        但重启或新会话加载时只会读到 DB 里的纯文本版本。
        """

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

        full_results = list(await asyncio.gather(*[_run_tool(b) for b in tool_blocks]))

        # 构建纯文本版本：将 image block 替换为 "[screenshot taken]" 占位符，
        # 保留 text block 的内容（如页面标题、URL 等元信息）
        history_results = []
        for r in full_results:
            content = r.get("content")
            if isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "image" for b in content
            ):
                text_parts = [
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                history_results.append({
                    **r,
                    "content": "\n".join(text_parts) + "\n[screenshot taken]" if text_parts else "[screenshot taken]",
                })
            else:
                history_results.append(r)

        return full_results, history_results

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
