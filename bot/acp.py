"""Claude Code integration — invoke via `claude -p` CLI with streaming JSON output."""

import asyncio
import json
import os
import shutil

from bot.config import ACP_COMMAND, ACP_CWD
from bot.logger import get_logger

log = get_logger("acp")

# Max output to return to Claude (prevent context overflow)
MAX_OUTPUT_CHARS = 8000


async def run_prompt(task: str, cwd: str | None = None, timeout: int = 300) -> str:
    """Send a coding task to Claude Code and return the result."""
    work_dir = cwd or ACP_CWD or os.getcwd()
    cmd = _build_command(task)

    log.info("claude_code → %s (cwd=%s, timeout=%ds)", task[:80], work_dir, timeout)

    env = {**os.environ}
    env.pop("CLAUDECODE", None)  # allow nested invocation

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=work_dir,
        env=env,
    )

    text_chunks: list[str] = []
    tool_log: list[str] = []

    try:
        async def read_stream():
            while proc.stdout:
                line = await proc.stdout.readline()
                if not line:
                    break

                line_str = line.decode(errors="replace").strip()
                if not line_str:
                    continue

                try:
                    event = json.loads(line_str)
                except json.JSONDecodeError:
                    # Plain text output (non-JSON mode fallback)
                    text_chunks.append(line_str)
                    continue

                _handle_event(event, text_chunks, tool_log)

        await asyncio.wait_for(read_stream(), timeout=timeout)

    except asyncio.TimeoutError:
        log.warning("claude_code timed out after %ds", timeout)
        proc.kill()
        text_chunks.append(f"\n[Timed out after {timeout}s]")

    # Wait for process to finish
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()

    # Read stderr for errors
    stderr_data = b""
    if proc.stderr:
        try:
            stderr_data = await asyncio.wait_for(proc.stderr.read(), timeout=3)
        except asyncio.TimeoutError:
            pass

    if proc.returncode and proc.returncode != 0 and not text_chunks:
        err_msg = stderr_data.decode(errors="replace").strip() if stderr_data else f"exit code {proc.returncode}"
        log.error("claude_code failed: %s", err_msg[:200])
        return f"[Claude Code error: {err_msg[:500]}]"

    # Combine text output
    result = "".join(text_chunks)

    # Append tool activity summary if any
    if tool_log:
        result += "\n\n--- Tool Activity ---\n" + "\n".join(tool_log)

    if not result.strip():
        result = "[No output from Claude Code]"

    if len(result) > MAX_OUTPUT_CHARS:
        result = result[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(result)} chars total]"

    log.info("claude_code ✓ %d chars, %d tool calls", len(result), len(tool_log))
    return result


def _handle_event(event: dict, text_chunks: list[str], tool_log: list[str]) -> None:
    """Parse a stream-json event from Claude Code CLI."""
    etype = event.get("type", "")
    subtype = event.get("subtype", "")

    if etype == "assistant" and subtype == "text":
        text_chunks.append(event.get("text", ""))

    elif etype == "assistant" and subtype == "tool_use":
        tool_name = event.get("tool", "unknown")
        log.info("claude_code tool: %s", tool_name)

    elif etype == "tool" and subtype == "result":
        tool_name = event.get("tool", "unknown")
        # Don't log full output (can be huge), just note it
        tool_log.append(f"• {tool_name}: done")

    elif etype == "result":
        # Final result event
        if subtype == "error":
            err = event.get("error", "unknown error")
            text_chunks.append(f"\n[Error: {err}]")
            log.error("claude_code result error: %s", err)
        else:
            # "success" — the result text is usually already in assistant chunks
            final_text = event.get("result", "")
            if final_text and not text_chunks:
                text_chunks.append(final_text)

    elif etype == "system":
        # System messages (session info, etc.)
        log.debug("claude_code system: %s", event.get("message", ""))


async def shutdown() -> None:
    """No persistent process to clean up in CLI mode."""
    pass


def _build_command(task: str) -> list[str]:
    """Build the claude CLI command."""
    if ACP_COMMAND:
        # Custom command — split and append task
        parts = ACP_COMMAND.split()
        parts.append(task)
        return parts

    # Default: claude CLI in print mode with streaming JSON
    cmd = [
        shutil.which("claude") or "claude",
        "-p", task,
        "--output-format", "stream-json",
        "--no-session-persistence",
        "--dangerously-skip-permissions",
    ]
    return cmd
