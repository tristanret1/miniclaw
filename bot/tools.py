"""Tool definitions and execution for Claude tool use."""

import asyncio
import os
import time

import httpx

from bot.config import GITHUB_TOKEN, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
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
                "description": "Session mode. 'isolated' (default): fresh each run. 'persistent': carry conversation history across runs.",
            },
            "context": {
                "type": "string",
                "description": "Extra system instructions for this job. Defines the job's personality, output format, focus areas, language, etc.",
            },
            "model": {
                "type": "string",
                "description": "Model override (e.g. 'claude-haiku-4-5-20251001' for simple tasks). Empty = use global default.",
            },
            "delivery_channel": {
                "type": "string",
                "enum": ["discord", "sms", "imessage"],
                "description": "Delivery channel: 'discord' (default) sends to Discord channel_id, 'sms' sends SMS via Twilio, 'imessage' sends via iMessage. For sms/imessage, channel_id should be E.164 phone number or Apple ID.",
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

PHONE_CALL_TOOL = {
    "name": "phone_call",
    "description": (
        "Make a phone call using Twilio and speak a message via TTS (text-to-speech). "
        "Use this for urgent notifications, reminders, or when the user explicitly asks "
        "to be called. The message will be read aloud to the recipient."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient phone number in E.164 format (e.g. +14155551234).",
            },
            "message": {
                "type": "string",
                "description": "The text message to speak via TTS.",
            },
            "language": {
                "type": "string",
                "description": "TTS language/voice (default: zh-CN). Examples: en-US, ja-JP, fr-FR.",
            },
        },
        "required": ["to", "message"],
    },
}

IMESSAGE_SEND_TOOL = {
    "name": "imessage_send",
    "description": (
        "Send an iMessage to a phone number or Apple ID email. "
        "Requires the imsg CLI tool to be installed on the host Mac. "
        "Use this when the user asks to send an iMessage."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient phone number (E.164) or Apple ID email.",
            },
            "message": {
                "type": "string",
                "description": "The message to send.",
            },
        },
        "required": ["to", "message"],
    },
}

SMS_TOOL = {
    "name": "sms",
    "description": (
        "Send an SMS text message via Twilio. "
        "Use this for notifications, reminders, or when the user asks to be texted."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient phone number in E.164 format (e.g. +14155551234).",
            },
            "message": {
                "type": "string",
                "description": "The text message to send (max 1600 characters).",
            },
        },
        "required": ["to", "message"],
    },
}

ALL_TOOLS = [
    EXEC_TOOL, MEMORY_SAVE_TOOL, MEMORY_SEARCH_TOOL, CLAUDE_CODE_TOOL,
    CRON_CREATE_TOOL, CRON_LIST_TOOL, CRON_DELETE_TOOL, PHONE_CALL_TOOL, SMS_TOOL,
    IMESSAGE_SEND_TOOL,
]  # DISCORD_SEND_TOOL


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


async def run_sms(to: str, message: str) -> str:
    """Send an SMS via Twilio REST API."""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER]):
        return "Error: Twilio credentials not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER)"

    log.info("sms → to=%s len=%d", to, len(message))

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    payload = {
        "To": to,
        "From": TWILIO_FROM_NUMBER,
        "Body": message[:1600],
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                data=payload,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                timeout=30,
            )

        if resp.status_code == 201:
            data = resp.json()
            sid = data.get("sid", "unknown")
            log.info("sms ✓ sid=%s to=%s", sid, to)
            return f"SMS sent successfully (SID: {sid}) to {to}."
        else:
            error = resp.text[:500]
            log.error("sms ✗ status=%d: %s", resp.status_code, error)
            return f"Error: Twilio returned {resp.status_code} — {error}"
    except Exception as e:
        log.error("sms ✗ exception: %s", e)
        return f"Error sending SMS: {e}"


async def run_phone_call(to: str, message: str, language: str = "zh-CN") -> str:
    """Make a TTS phone call via Twilio REST API."""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER]):
        return "Error: Twilio credentials not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER)"

    log.info("phone_call → to=%s lang=%s len=%d", to, language, len(message))

    # Build TwiML inline — Twilio accepts a URL or inline TwiML via the Twiml parameter
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say language="{language}">{message}</Say>'
        "</Response>"
    )

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Calls.json"
    payload = {
        "To": to,
        "From": TWILIO_FROM_NUMBER,
        "Twiml": twiml,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                data=payload,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                timeout=30,
            )

        if resp.status_code == 201:
            data = resp.json()
            sid = data.get("sid", "unknown")
            log.info("phone_call ✓ call_sid=%s to=%s", sid, to)
            return f"Call initiated successfully (SID: {sid}). Message will be spoken to {to}."
        else:
            error = resp.text[:500]
            log.error("phone_call ✗ status=%d: %s", resp.status_code, error)
            return f"Error: Twilio returned {resp.status_code} — {error}"
    except Exception as e:
        log.error("phone_call ✗ exception: %s", e)
        return f"Error making call: {e}"


async def handle_tool_call(tool_name: str, tool_input: dict, memory_dir=None) -> str:
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
            memory_dir=memory_dir,
        )
    if tool_name == "memory_search":
        return memory.search(
            query=tool_input["query"],
            max_results=tool_input.get("max_results", 10),
            memory_dir=memory_dir,
        )
    if tool_name == "claude_code":
        timeout = min(max(tool_input.get("timeout", 300), 30), 600)
        return await acp.run_prompt(
            task=tool_input["task"],
            cwd=tool_input.get("cwd"),
            timeout=timeout,
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
            delivery_channel=tool_input.get("delivery_channel", "discord"),
        )
    if tool_name == "cron_list":
        from bot import cron
        return cron.list_jobs(
            include_disabled=tool_input.get("include_disabled", False),
        )
    if tool_name == "cron_delete":
        from bot import cron
        return cron.delete_job(job_id=tool_input["job_id"])
    if tool_name == "sms":
        return await run_sms(
            to=tool_input["to"],
            message=tool_input["message"],
        )
    if tool_name == "phone_call":
        return await run_phone_call(
            to=tool_input["to"],
            message=tool_input["message"],
            language=tool_input.get("language", "zh-CN"),
        )
    if tool_name == "imessage_send":
        from bot.imessage_gateway import get_gateway_client, send_imessage, run_imessage_send
        client = get_gateway_client()
        if client:
            return await send_imessage(client, to=tool_input["to"], message=tool_input["message"])
        return await run_imessage_send(to=tool_input["to"], message=tool_input["message"])
    log.warning("unknown tool called: %s", tool_name)
    return f"Unknown tool: {tool_name}"
