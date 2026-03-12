"""Tool definitions and execution for Claude tool use."""

import asyncio
import os
import time

from bot.logger import get_logger
from bot import acp, memory

log = get_logger("tools")

# Max output length to avoid flooding Discord / Claude context
MAX_OUTPUT_CHARS = 4000
DEFAULT_TIMEOUT = 30


EXEC_TOOL = {
    "name": "exec",
    "description": (
        "Execute a shell command on the host machine and return its output. "
        "Use this for system tasks like listing files, checking disk usage, "
        "running scripts, installing packages, etc."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30, max 120).",
            },
            "workdir": {
                "type": "string",
                "description": "Working directory for the command.",
            },
        },
        "required": ["command"],
    },
}

MEMORY_SAVE_TOOL = {
    "name": "memory_save",
    "description": (
        "Save a piece of information to long-term memory. Use this to remember "
        "user preferences, important facts, decisions, or anything worth recalling later. "
        "Memories are stored as daily Markdown logs."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The information to remember.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags for categorization (e.g. ['preference', 'user']).",
            },
        },
        "required": ["content"],
    },
}

MEMORY_SEARCH_TOOL = {
    "name": "memory_search",
    "description": (
        "Search long-term memory for previously saved information. "
        "Use this when the user references past conversations, preferences, "
        "or facts that may have been stored."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords to search for in memory.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default 10).",
            },
        },
        "required": ["query"],
    },
}

CLAUDE_CODE_TOOL = {
    "name": "claude_code",
    "description": (
        "Delegate a coding task to Claude Code (an autonomous coding agent) via ACP. "
        "Use this for complex programming tasks: writing code, debugging, refactoring, "
        "reading/editing files in a project, running tests, git operations, etc. "
        "Claude Code has full access to the filesystem and terminal."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The coding task to delegate. Be specific about what to do, which files, and expected outcome.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the task (defaults to ACP_CWD or current dir).",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 300, max 600).",
            },
        },
        "required": ["task"],
    },
}

ALL_TOOLS = [EXEC_TOOL, MEMORY_SAVE_TOOL, MEMORY_SEARCH_TOOL, CLAUDE_CODE_TOOL]


async def run_exec(command: str, timeout: int = DEFAULT_TIMEOUT, workdir: str | None = None) -> str:
    timeout = min(max(timeout, 1), 120)
    cwd = workdir if workdir and os.path.isdir(workdir) else None

    log.info("exec → %s (timeout=%ds, cwd=%s)", command, timeout, cwd or ".")
    start = time.monotonic()

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        elapsed = time.monotonic() - start
        log.warning("exec ✗ timed out after %.1fs: %s", elapsed, command)
        return f"[Timed out after {timeout}s]"

    elapsed = time.monotonic() - start
    output = ""
    if stdout:
        output += stdout.decode(errors="replace")
    if stderr:
        output += ("\n--- stderr ---\n" + stderr.decode(errors="replace"))

    if not output.strip():
        output = f"[No output, exit code {proc.returncode}]"
    elif proc.returncode != 0:
        output += f"\n[exit code {proc.returncode}]"

    truncated = len(output) > MAX_OUTPUT_CHARS
    if truncated:
        output = output[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(output)} chars total]"

    if proc.returncode == 0:
        log.info("exec ✓ exit=0 %.1fs (%d chars%s): %s", elapsed, len(output), " truncated" if truncated else "", command)
    else:
        log.warning("exec ✗ exit=%s %.1fs: %s", proc.returncode, elapsed, command)
    log.debug("exec output:\n%s", output[:500])

    return output


async def handle_tool_call(tool_name: str, tool_input: dict) -> str:
    if tool_name == "exec":
        return await run_exec(
            command=tool_input["command"],
            timeout=tool_input.get("timeout", DEFAULT_TIMEOUT),
            workdir=tool_input.get("workdir"),
        )
    if tool_name == "memory_save":
        return memory.save(
            content=tool_input["content"],
            tags=tool_input.get("tags"),
        )
    if tool_name == "memory_search":
        return memory.search(
            query=tool_input["query"],
            max_results=tool_input.get("max_results", 10),
        )
    if tool_name == "claude_code":
        timeout = min(max(tool_input.get("timeout", 300), 30), 600)
        return await acp.run_prompt(
            task=tool_input["task"],
            cwd=tool_input.get("cwd"),
            timeout=timeout,
        )
    log.warning("unknown tool called: %s", tool_name)
    return f"Unknown tool: {tool_name}"
