"""Tool definitions and execution for Claude tool use."""

__all__ = ["ALL_TOOLS", "handle_tool_call"]

from bot import acp
from bot.storage import memory
from bot.config import get_config
from bot.constants import EXEC_DEFAULT_TIMEOUT
from bot.logger import get_logger
from bot.tools.calendar import GOOGLE_CALENDAR_TOOL, run_google_calendar
from bot.tools.claude_code import CLAUDE_CODE_TOOL
from bot.tools.cron_tools import CRON_CREATE_TOOL, CRON_DELETE_TOOL, CRON_LIST_TOOL
from bot.tools.discord_send import DISCORD_SEND_TOOL, run_discord_send
from bot.tools.exec import EXEC_TOOL, MAX_OUTPUT_CHARS, run_exec
from bot.tools.health_tools import HEALTH_GOAL_TOOL, HEALTH_LOG_TOOL, HEALTH_STATS_TOOL
from bot.tools.imessage_tools import IMESSAGE_SEND_TOOL
from bot.tools.memory_tools import MEMORY_SAVE_TOOL, MEMORY_SEARCH_TOOL
from bot.tools.sms import PHONE_CALL_TOOL, SMS_TOOL, run_phone_call, run_sms
from bot.tools.voice_tools import VOICE_ANNOUNCE_TOOL
from bot.tools.browser import BROWSER_TOOL
from bot.tools.twitter import TWITTER_TOOL
from bot.tools.reddit import REDDIT_TOOL
from bot.tools.kb import KB_TOOL

log = get_logger("tools")

DEFAULT_TIMEOUT = EXEC_DEFAULT_TIMEOUT

ALL_TOOLS = [
    EXEC_TOOL, MEMORY_SAVE_TOOL, MEMORY_SEARCH_TOOL, CLAUDE_CODE_TOOL,
    CRON_CREATE_TOOL, CRON_LIST_TOOL, CRON_DELETE_TOOL, PHONE_CALL_TOOL, SMS_TOOL,
    IMESSAGE_SEND_TOOL, BROWSER_TOOL, TWITTER_TOOL, REDDIT_TOOL, KB_TOOL,
]  # DISCORD_SEND_TOOL

_cfg = get_config()
if _cfg.gateway.voice.enabled:
    ALL_TOOLS.append(VOICE_ANNOUNCE_TOOL)

if _cfg.services.google_calendar.enabled:
    ALL_TOOLS.append(GOOGLE_CALENDAR_TOOL)

if _cfg.services.health.enabled:
    ALL_TOOLS.extend([HEALTH_LOG_TOOL, HEALTH_STATS_TOOL, HEALTH_GOAL_TOOL])


async def handle_tool_call(tool_name: str, tool_input: dict, memory_dir=None,
                           agent_name: str = "default") -> str:
    if tool_name == "exec":
        return await run_exec(
            command=tool_input["command"],
            timeout=tool_input.get("timeout", DEFAULT_TIMEOUT),
            workdir=tool_input.get("workdir"),
        )
    if tool_name == "memory_save":
        return await memory.save(
            content=tool_input["content"],
            tags=tool_input.get("tags"),
            memory_dir=memory_dir,
            agent_name=agent_name,
        )
    if tool_name == "memory_search":
        return await memory.search(
            query=tool_input["query"],
            max_results=tool_input.get("max_results", 10),
            memory_dir=memory_dir,
            agent_name=agent_name,
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
        from bot.services import cron
        # Embed agent name in context for delivery routing
        context = tool_input.get("context", "")
        agent_tag = tool_input.get("agent", "")
        if agent_tag:
            context = f"delivery_agent:{agent_tag}\n{context}" if context else f"delivery_agent:{agent_tag}"
        return await cron.create_job(
            name=tool_input["name"],
            schedule_type=tool_input["schedule_type"],
            schedule_value=tool_input["schedule_value"],
            payload=tool_input["payload"],
            channel_id=tool_input["channel_id"],
            timezone=tool_input.get("timezone", ""),
            session_mode=tool_input.get("session_mode", "isolated"),
            context=context,
            model=tool_input.get("model", ""),
            delivery_channel=tool_input.get("delivery_channel", "discord"),
        )
    if tool_name == "cron_list":
        from bot.services import cron
        return await cron.list_jobs(
            include_disabled=tool_input.get("include_disabled", False),
        )
    if tool_name == "cron_delete":
        from bot.services import cron
        return await cron.delete_job(job_id=tool_input["job_id"])
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
        from bot.channel.imessage import get_gateway_client, send_imessage, run_imessage_send
        client = get_gateway_client()
        if client:
            return await send_imessage(client, to=tool_input["to"], message=tool_input["message"])
        return await run_imessage_send(to=tool_input["to"], message=tool_input["message"])
    if tool_name == "voice_announce":
        from bot.channel.voice import announce
        return await announce(
            message=tool_input["message"],
            source=tool_input.get("source", agent_name),
        )
    if tool_name == "google_calendar":
        gcal_input = {k: v for k, v in tool_input.items() if k != "action"}
        return await run_google_calendar(action=tool_input.get("action", ""), **gcal_input)
    if tool_name == "health_log":
        from bot.services import health
        log_type = tool_input.get("type", "")
        date = tool_input.get("date", "")
        if log_type == "weight":
            return await health.log_weight(
                value=tool_input.get("value", 0),
                unit=tool_input.get("unit", "kg"),
                date=date,
            )
        if log_type == "sleep":
            return await health.log_sleep(
                hours=tool_input.get("hours", 0),
                quality=tool_input.get("quality", ""),
                bedtime=tool_input.get("bedtime", ""),
                wake_time=tool_input.get("wake_time", ""),
                date=date,
            )
        if log_type == "exercise":
            return await health.log_exercise(
                activity=tool_input.get("activity", ""),
                duration_minutes=tool_input.get("duration_minutes", 0),
                intensity=tool_input.get("intensity", "moderate"),
                calories=tool_input.get("calories", 0),
                notes=tool_input.get("notes", ""),
                date=date,
            )
        return f"Unknown health log type: {log_type}. Use: weight, sleep, exercise."
    if tool_name == "health_stats":
        from bot.services import health
        return await health.get_stats(
            stat_type=tool_input.get("stat_type", "overview"),
            days=tool_input.get("days", 30),
        )
    if tool_name == "health_goal":
        from bot.services import health
        return await health.set_weight_goal(
            start_weight=tool_input["start_weight"],
            target_weight=tool_input["target_weight"],
            target_date=tool_input["target_date"],
        )
    if tool_name == "browser":
        from bot.tools.browser import run_browser
        action = tool_input.get("action", "")
        kwargs = {k: v for k, v in tool_input.items() if k != "action"}
        result = await run_browser(action, **kwargs)
        if isinstance(result, dict) and result.get("screenshot_base64"):
            # Return screenshot as image content for Claude's vision
            screenshot_b64 = result.pop("screenshot_base64")
            text_info = ", ".join(f"{k}={v}" for k, v in result.items() if v)
            return [
                {"type": "text", "text": text_info},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": screenshot_b64,
                    },
                },
            ]
        if isinstance(result, dict):
            return "\n".join(f"{k}: {v}" for k, v in result.items() if v)
        return result
    if tool_name == "twitter":
        from bot.tools.twitter import run_twitter
        action = tool_input.get("action", "")
        kwargs = {k: v for k, v in tool_input.items() if k != "action"}
        return await run_twitter(action, **kwargs)
    if tool_name == "reddit":
        from bot.tools.reddit import run_reddit
        action = tool_input.get("action", "")
        kwargs = {k: v for k, v in tool_input.items() if k != "action"}
        return await run_reddit(action, **kwargs)
    if tool_name == "kb":
        from bot.services import kb as kb_svc
        action = tool_input.get("action", "")
        if action == "ingest":
            url = tool_input.get("url", "")
            if not url:
                return "Error: url is required for ingest"
            return await kb_svc.ingest(
                url=url,
                source_type=tool_input.get("type", "auto"),
            )
        if action == "query":
            question = tool_input.get("question", "")
            if not question:
                return "Error: question is required for query"
            return await kb_svc.query(question=question)
        if action == "list":
            return kb_svc.list_kb()
        if action == "status":
            return kb_svc.status()
        if action == "compile":
            return await kb_svc.compile()
        return f"Error: unknown kb action '{action}'"
    log.warning("unknown tool called: %s", tool_name)
    return f"Unknown tool: {tool_name}"
