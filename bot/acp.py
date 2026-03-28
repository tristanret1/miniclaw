"""Claude Code integration via claude-agent-sdk (ACP)."""

import os

from claude_agent_sdk import query
from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from bot.config import ACP_CWD
from bot.constants import ACP_MAX_OUTPUT_CHARS
from bot.logger import get_logger

log = get_logger("acp")

MAX_OUTPUT_CHARS = ACP_MAX_OUTPUT_CHARS


async def run_prompt(task: str, cwd: str | None = None, timeout: int = 300) -> str:
    """Send a coding task to Claude Code and return the result."""
    work_dir = cwd or ACP_CWD or os.getcwd()

    log.info("claude_code → %s (cwd=%s)", task[:100], work_dir)

    options = ClaudeAgentOptions(
        cwd=work_dir,
        permission_mode="bypassPermissions",
        max_turns=20,
    )

    text_chunks: list[str] = []
    tool_log: list[str] = []

    try:
        async for msg in query(prompt=task, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_chunks.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        log.info("claude_code tool: %s", block.name)
                        tool_log.append(f"• {block.name}")

            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    log.error("claude_code error: %s", msg.result)
                    text_chunks.append(f"\n[Error: {msg.result}]")
                else:
                    log.info("claude_code completed (%d turns, $%.4f, %dms)",
                             msg.num_turns, msg.total_cost_usd or 0, msg.duration_ms)

    except Exception as e:
        log.error("claude_code failed: %s", e)
        return f"[Claude Code error: {e}]"

    result = "".join(text_chunks)

    if tool_log:
        result += "\n\n--- Tool Activity ---\n" + "\n".join(tool_log)

    if not result.strip():
        result = "[No output from Claude Code]"

    if len(result) > MAX_OUTPUT_CHARS:
        result = result[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(result)} chars total]"

    log.info("claude_code ✓ %d chars, %d tool calls", len(result), len(tool_log))
    return result


async def shutdown() -> None:
    """No persistent state to clean up."""
    pass
