"""Tool definitions and execution for Claude tool use."""

import asyncio
import os
import time

import httpx

from bot.config import BRAVE_API_KEY, GITHUB_TOKEN
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

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for real-time information using Brave Search API. "
        "Use this when the user asks about current events, recent news, live data, "
        "or anything that requires up-to-date information beyond your knowledge cutoff."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "count": {
                "type": "integer",
                "description": "Number of results to return (1-10, default 5).",
            },
            "freshness": {
                "type": "string",
                "description": "Time filter: 'day', 'week', 'month', or 'year'.",
            },
        },
        "required": ["query"],
    },
}

DISCORD_SEND_TOOL = {
    "name": "discord_send",
    "description": (
        "Send a message to a specified Discord channel proactively. "
        "Use this to deliver notifications, reminders, or any content to a channel "
        "without waiting for user interaction."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "The Discord channel ID to send the message to.",
            },
            "message": {
                "type": "string",
                "description": "The message content to send (max 2000 characters).",
            },
            "ephemeral": {
                "type": "boolean",
                "description": "If true, only the caller can see the message (default false). Only works in interaction contexts.",
            },
        },
        "required": ["channel_id", "message"],
    },
}

CRON_CREATE_TOOL = {
    "name": "cron_create",
    "description": (
        "Create a scheduled/recurring task. The task message will be sent to "
        "Claude at the scheduled time, and the response delivered to a Discord channel. "
        "Use 'context' to define per-job personality/instructions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Human-readable name for this job.",
            },
            "schedule_type": {
                "type": "string",
                "enum": ["every", "cron", "at"],
                "description": "Schedule type: 'every' for interval, 'cron' for cron expression, 'at' for one-shot.",
            },
            "schedule_value": {
                "type": "string",
                "description": "Schedule value. every: '30m','2h','1d'. cron: '0 8 * * *'. at: ISO time or '+20m'.",
            },
            "payload": {
                "type": "string",
                "description": "The message/task to send to Claude when the job fires.",
            },
            "channel_id": {
                "type": "string",
                "description": "Discord channel ID to deliver results to.",
            },
            "timezone": {
                "type": "string",
                "description": "IANA timezone (default: America/Vancouver).",
            },
            "session_mode": {
                "type": "string",
                "enum": ["isolated", "persistent"],
                "description": "Session mode. 'isolated' (default): fresh each run. 'persistent': carry conversation history across runs for diff/comparison.",
            },
            "context": {
                "type": "string",
                "description": "Extra system instructions for this job. Defines the job's personality, output format, focus areas, language, etc.",
            },
            "model": {
                "type": "string",
                "description": "Model override (e.g. 'claude-haiku-4-5-20251001' for simple tasks). Empty = use global default.",
            },
        },
        "required": ["name", "schedule_type", "schedule_value", "payload", "channel_id"],
    },
}

CRON_LIST_TOOL = {
    "name": "cron_list",
    "description": "List all scheduled tasks with their status and next run time.",
    "input_schema": {
        "type": "object",
        "properties": {
            "include_disabled": {
                "type": "boolean",
                "description": "Include disabled/completed jobs (default: false).",
            },
        },
    },
}

CRON_DELETE_TOOL = {
    "name": "cron_delete",
    "description": "Delete a scheduled task by ID or name.",
    "input_schema": {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "Job ID or name to delete.",
            },
        },
        "required": ["job_id"],
    },
}

ALL_TOOLS = [
    EXEC_TOOL, MEMORY_SAVE_TOOL, MEMORY_SEARCH_TOOL, CLAUDE_CODE_TOOL, WEB_SEARCH_TOOL,
    CRON_CREATE_TOOL, CRON_LIST_TOOL, CRON_DELETE_TOOL,
]


async def run_exec(command: str, timeout: int = DEFAULT_TIMEOUT, workdir: str | None = None) -> str:
    timeout = min(max(timeout, 1), 120)
    cwd = workdir if workdir and os.path.isdir(workdir) else None

    log.info("exec → %s (timeout=%ds, cwd=%s)", command, timeout, cwd or ".")
    start = time.monotonic()

    # Inject GitHub token so gh/git commands can authenticate
    env = os.environ.copy()
    if GITHUB_TOKEN:
        env["GH_TOKEN"] = GITHUB_TOKEN
        env["GITHUB_TOKEN"] = GITHUB_TOKEN

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
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


async def run_web_search(query: str, count: int = 5, freshness: str | None = None) -> str:
    """Search the web via Brave Search API and return formatted results."""
    if not BRAVE_API_KEY:
        return "Error: BRAVE_API_KEY not configured. Add it to .env to enable web search."

    count = min(max(count, 1), 10)
    log.info("web_search → %r (count=%d, freshness=%s)", query, count, freshness)
    start = time.monotonic()

    params: dict[str, str | int] = {"q": query, "count": count}
    if freshness in ("day", "week", "month", "year"):
        params["freshness"] = freshness

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params=params,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": BRAVE_API_KEY,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        log.error("web_search ✗ HTTP %s: %s", e.response.status_code, e.response.text[:200])
        return f"Search failed (HTTP {e.response.status_code})"
    except Exception as e:
        log.error("web_search ✗ %s", e)
        return f"Search failed: {e}"

    elapsed = time.monotonic() - start
    results = data.get("web", {}).get("results", [])

    if not results:
        log.info("web_search ✓ no results (%.1fs)", elapsed)
        return "No results found."

    lines: list[str] = []
    for i, r in enumerate(results[:count], 1):
        title = r.get("title", "")
        url = r.get("url", "")
        desc = r.get("description", "")
        age = r.get("age", "")
        line = f"{i}. **{title}**\n   {url}\n   {desc}"
        if age:
            line += f"\n   ({age})"
        lines.append(line)

    output = f"Search results for: {query}\n\n" + "\n\n".join(lines)

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... [truncated]"

    log.info("web_search ✓ %d results (%.1fs)", len(results), elapsed)
    return output


async def run_discord_send(channel_id: str, message: str, ephemeral: bool = False) -> str:
    """Send a message to a Discord channel using the bot client."""
    from bot.client import bot  # lazy import to avoid circular dependency

    log.info("discord_send → channel=%s len=%d ephemeral=%s", channel_id, len(message), ephemeral)

    try:
        channel = bot.get_channel(int(channel_id))
        if channel is None:
            # Fall back to fetch if not in cache
            channel = await bot.fetch_channel(int(channel_id))
    except (ValueError, Exception) as e:
        log.error("discord_send ✗ failed to resolve channel %s: %s", channel_id, e)
        return f"Error: could not find channel {channel_id} – {e}"

    try:
        # Truncate message to Discord's 2000 char limit per message
        chunks = [message[i : i + 2000] for i in range(0, len(message), 2000)]
        for chunk in chunks:
            await channel.send(chunk)
        log.info("discord_send ✓ sent %d chunk(s) to channel %s", len(chunks), channel_id)
        return f"Message sent to channel {channel_id} ({len(chunks)} part(s))."
    except Exception as e:
        log.error("discord_send ✗ failed to send to channel %s: %s", channel_id, e)
        return f"Error sending message: {e}"


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
    if tool_name == "web_search":
        return await run_web_search(
            query=tool_input["query"],
            count=tool_input.get("count", 5),
            freshness=tool_input.get("freshness"),
        )
    if tool_name == "discord_send":
        return await run_discord_send(
            channel_id=tool_input["channel_id"],
            message=tool_input["message"],
            ephemeral=tool_input.get("ephemeral", False),
        )
    if tool_name == "cron_create":
        from bot import cron
        return cron.create_job(
            name=tool_input["name"],
            schedule_type=tool_input["schedule_type"],
            schedule_value=tool_input["schedule_value"],
            payload=tool_input["payload"],
            channel_id=tool_input["channel_id"],
            timezone=tool_input.get("timezone", ""),
            session_mode=tool_input.get("session_mode", "isolated"),
            context=tool_input.get("context", ""),
            model=tool_input.get("model", ""),
        )
    if tool_name == "cron_list":
        from bot import cron
        return cron.list_jobs(
            include_disabled=tool_input.get("include_disabled", False),
        )
    if tool_name == "cron_delete":
        from bot import cron
        return cron.delete_job(job_id=tool_input["job_id"])
    log.warning("unknown tool called: %s", tool_name)
    return f"Unknown tool: {tool_name}"
