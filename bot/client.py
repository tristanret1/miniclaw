import asyncio
import random
from datetime import datetime

import discord
from bot import llm
from bot.agent import Agent
from bot.message import build_user_content
from bot.utils.discord import send_chunks
from bot.utils.session_keys import discord_key, greeting_key
from bot.config import (
    get_config,
    get_loaded_skills,
)
from bot.skills import match_skill_command, build_skill_user_message, build_skill_command_list
from bot.storage import memory
from bot.logger import get_logger

log = get_logger("client")

# ── User memory cache ────────────────────────────────────────────────────────
# Tracks {user_id: (username, display_name)} to avoid duplicate saves
_known_users: dict[int, tuple[str, str]] = {}

# Supported image MIME types for Claude vision
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

# Streaming: flush interval and buffer
_STREAM_FLUSH_INTERVAL = 0.1  # seconds between Discord edits
_STREAM_FLUSH_CHARS = 50     # min chars accumulated before edit

# Track whether cron has been started (only once across all agents)
_cron_started = False

# Active heartbeat runners (per agent name)
_heartbeat_runners: dict[str, object] = {}


def _extract_image_urls(message: discord.Message) -> list[str]:
    """Extract image URLs from message attachments and embeds."""
    urls = []
    for att in message.attachments:
        if att.content_type and att.content_type.split(";")[0] in _IMAGE_TYPES:
            urls.append(att.url)
    for embed in message.embeds:
        if embed.image and embed.image.url:
            urls.append(embed.image.url)
        if embed.thumbnail and embed.thumbnail.url:
            urls.append(embed.thumbnail.url)
    return urls


def should_auto_reply(message: discord.Message, bot_user) -> bool:
    cfg = get_config().discord.auto_reply
    if not cfg.enabled:
        return False
    if message.guild is None:
        return False
    if bot_user in message.mentions:
        return False
    channels = [c for c in cfg.channels if c]
    if channels and str(message.channel.id) not in channels:
        return False
    keywords = [k for k in cfg.keywords if k]
    if keywords:
        content_lower = message.content.lower()
        keyword_triggered = any(k.strip().lower() in content_lower for k in keywords if k.strip())
        if not keyword_triggered:
            return False
    return random.random() < cfg.chance


async def _send_greeting(bot: discord.Client, agent: Agent) -> None:
    """Send a startup greeting with a summary of past conversations."""
    try:
        greeting_channel_id_str = get_config().discord.greeting_channel_id
        if not greeting_channel_id_str:
            log.warning("_send_greeting called but discord.greeting_channel_id not configured")
            return
        greeting_channel_id = int(greeting_channel_id_str)

        channel = bot.get_channel(greeting_channel_id)
        if channel is None:
            channel = await bot.fetch_channel(greeting_channel_id)

        session_key = greeting_key(greeting_channel_id)

        # Load history and build a summary instead of carrying full history
        from bot.storage.session import SessionManager
        from bot.message import extract_text
        session_mgr = agent.session_mgr or SessionManager()
        history = await session_mgr.get_history(session_key)

        summary = ""
        log.debug("greeting: loaded %d history messages for session %s", len(history), session_key)
        if history:
            # Extract text from history, truncate to keep summary request small
            lines = []
            for msg in history:
                role = msg.get("role", "")
                text = extract_text(msg.get("content", ""))
                if text.strip():
                    lines.append(f"{role}: {text[:200]}")
            history_text = "\n".join(lines[-30:])  # last 30 messages max
            log.debug("greeting: history_text (%d chars):\n%s", len(history_text), history_text[:1000])

            if history_text.strip():
                summary = await llm.reply(
                    f"{session_key}:summary:{int(datetime.now().timestamp())}",
                    f"请用500字以内总结以下对话历史的要点，只输出总结内容：\n\n{history_text}",
                    agent=agent,
                )
                log.debug("greeting: summary result (%d chars): %s", len(summary), summary[:500])
            else:
                log.debug("greeting: history_text is empty after extraction")

            # Clear the greeting session so it starts fresh
            await session_mgr.clear(session_key)
        else:
            log.debug("greeting: no history found for session %s", session_key)

        # Build greeting prompt with summary context
        prompt = "你刚刚上线了，用一句话跟大家打个招呼吧。"
        if summary.strip():
            prompt = f"以下是你之前运行时发生的所有记忆汇总：\n\n{summary[:500]}\n\n---\n\n{prompt}"
        log.debug("greeting: final prompt: %s", prompt[:500])

        greeting = await llm.reply(session_key, prompt, agent=agent)
        await channel.send(greeting[:2000])
        log.info("startup greeting sent to channel %s", greeting_channel_id)
    except Exception as e:
        log.error("failed to send startup greeting: %s", e)


def create_bot(agent: Agent) -> discord.Client:
    """Create a Discord client bound to a specific agent."""
    intents = discord.Intents.default()
    intents.message_content = True
    bot = discord.Client(intents=intents)

    async def _remember_user(message: discord.Message) -> None:
        """Save user info to memory if new or name changed."""
        user = message.author
        uid = user.id
        username = str(user)
        display_name = user.display_name

        cached = _known_users.get(uid)
        if cached and cached == (username, display_name):
            return

        _known_users[uid] = (username, display_name)

        channel_id = message.channel.id
        timestamp = datetime.now().isoformat(timespec="seconds")
        content = (
            f"用户信息: ID={uid}, 用户名={username}, "
            f"显示名={display_name}, 频道={channel_id}, 时间={timestamp}"
        )
        tags = ["user_profile"]

        try:
            result = await memory.save(content=content, tags=tags, source="system",
                                       memory_dir=agent.memory_dir,
                                       agent_name=agent.name)
            action = "updated" if cached else "recorded"
            log.info("user memory %s: %s (%s) → %s", action, username, display_name, result)
        except Exception as e:
            log.error("failed to save user memory for %s: %s", username, e)

    @bot.event
    async def on_ready():
        global _cron_started
        print(f"Agent '{agent.name}' online as {bot.user}")
        _cfg = get_config()
        if _cfg.discord.auto_reply.enabled:
            print(f"Auto-reply enabled with {_cfg.discord.auto_reply.chance*100}% chance")

        # Send startup greeting
        # await _send_greeting(bot, agent)

        # Start cron scheduler only once (first agent)
        if not _cron_started:
            if _cfg.services.cron.enabled:
                from bot.cron import get_scheduler
                scheduler = get_scheduler()
                await scheduler.start(bot)
                print("Cron scheduler started")
            _cron_started = True

        # Start heartbeat for this agent
        hb_cfg = _cfg.gateway.heartbeat
        if hb_cfg.enabled and agent.name not in _heartbeat_runners:
            channel_id = hb_cfg.channel_id
            if channel_id:
                from bot.gateway.heartbeat import HeartbeatRunner

                async def _deliver_heartbeat(text: str, _bot=bot, _cid=channel_id) -> None:
                    """Deliver heartbeat message to configured Discord channel."""
                    try:
                        channel = _bot.get_channel(int(_cid))
                        if channel is None:
                            channel = await _bot.fetch_channel(int(_cid))
                        await send_chunks(channel, text)
                    except Exception as e:
                        log.error("heartbeat delivery to channel %s failed: %s", _cid, e)
                        raise

                runner = HeartbeatRunner(
                    agent=agent,
                    deliver_fn=_deliver_heartbeat,
                    channel_id=str(channel_id),
                    interval=hb_cfg.interval,
                    active_hours_start=hb_cfg.active_start,
                    active_hours_end=hb_cfg.active_end,
                    active_hours_tz=hb_cfg.active_tz,
                    ack_max_chars=hb_cfg.ack_max_chars,
                    isolated_session=hb_cfg.isolated,
                )
                await runner.start()
                _heartbeat_runners[agent.name] = runner
                print(f"Heartbeat started for agent '{agent.name}' (every {hb_cfg.interval})")
            else:
                log.warning("heartbeat.enabled but heartbeat.channel_id not set — skipping")

    async def _send_streaming(message: discord.Message, session_key: str, user_content):
        """Stream Claude's reply, editing a single Discord message progressively."""
        buffer = ""
        sent_msg: discord.Message | None = None
        last_edit = 0.0
        last_edit_len = 0
        stream_start = asyncio.get_event_loop().time()

        async for chunk in llm.stream(session_key, user_content, agent=agent):
            buffer += chunk
            now = asyncio.get_event_loop().time()

            if not sent_msg:
                if len(buffer.strip()) >= 5 or (now - stream_start) >= 0.3:
                    display = buffer[:1990]
                    sent_msg = await message.reply(display + " ▍")
                    last_edit_len = len(buffer)
                    last_edit = now
            else:
                new_chars = len(buffer) - last_edit_len
                should_edit = (
                    (now - last_edit >= _STREAM_FLUSH_INTERVAL and new_chars >= _STREAM_FLUSH_CHARS)
                    or new_chars >= 100
                )

                if should_edit:
                    display = buffer[:1990]
                    await sent_msg.edit(content=display + " ▍")
                    last_edit_len = len(buffer)
                    last_edit = now

        if sent_msg:
            if len(buffer) <= 2000:
                await sent_msg.edit(content=buffer)
            else:
                await sent_msg.edit(content=buffer[:2000])
                await send_chunks(message.channel, buffer[2000:])
        elif buffer.strip():
            for i in range(0, len(buffer), 2000):
                await message.reply(buffer[i : i + 2000])
        else:
            await message.reply("[No response]")

    def _should_handle(message: discord.Message) -> bool:
        if message.guild is not None:
            return bot.user in message.mentions
        # DM — only allow whitelisted users
        allowed_dm_users = get_config().discord.allowed_dm_users
        if not allowed_dm_users or message.author.id not in allowed_dm_users:
            log.debug("DM from %s (%s) blocked — not in allowed_dm_users", message.author, message.author.id)
            return False
        return True

    def _extract_content(message: discord.Message) -> str:
        content = message.content
        if message.guild is not None:
            for mention_str in [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]:
                content = content.replace(mention_str, "").strip()
        return content

    async def _process_message(message: discord.Message) -> None:
        content = _extract_content(message)
        image_urls = _extract_image_urls(message)

        if not content.strip() and not image_urls:
            return

        # Handle /heartbeat — manual trigger
        if content.strip().lower() == "/heartbeat":
            runner = _heartbeat_runners.get(agent.name)
            if runner is None:
                await message.reply("Heartbeat not enabled. Set `HEARTBEAT_ENABLED=true` and `HEARTBEAT_CHANNEL_ID`.")
                return
            await message.reply("Running heartbeat...")
            result = await runner.wake(reason="manual")
            await message.reply(f"Heartbeat result: `{result}`")
            return

        # Handle /skills list command
        if content.strip().lower() in ("/skills", "/skill"):
            skills = get_loaded_skills()
            await message.reply(build_skill_command_list(skills))
            return

        # Handle /skill-name commands
        if content.startswith("/"):
            skills = get_loaded_skills()
            result = match_skill_command(content, skills)
            if result:
                skill, args = result
                log.info("skill command: /%s args=%r", skill.name, args[:100] if args else "")
                content = build_skill_user_message(skill, args)

        session_key = discord_key(message.channel.id, message.author.id)

        # Prepend sender metadata so the LLM knows who sent the message and when
        sender = message.author.display_name
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(get_config().services.cron.timezone)
        local_time = message.created_at.astimezone(tz)
        timestamp = local_time.strftime("%Y-%m-%d %H:%M %Z")
        channel_name = getattr(message.channel, "name", "DM")
        meta = f"[{sender} (ID:{message.author.id}) · #{channel_name} · {timestamp}]\n"
        content = meta + content

        user_content = build_user_content(content, image_urls if image_urls else None)

        if image_urls:
            log.info("multimodal message: %d image(s) + %d chars text", len(image_urls), len(content))

        from bot import hooks
        hooks.fire_working(agent.name, f"Replying in #{getattr(message.channel, 'name', 'DM')}")

        async with message.channel.typing():
            try:
                reply_text = await llm.reply(session_key, user_content, agent=agent)
                for i in range(0, len(reply_text), 2000):
                    await message.reply(reply_text[i : i + 2000])
            except Exception as e:
                log.error("reply error: %s", e)
                await message.reply(f"Error: {e}")
            finally:
                hooks.fire_idle(agent.name)

    @bot.event
    async def on_message(message: discord.Message):
        if message.author == bot.user:
            return

        # 5% chance to ignore messages from other bots
        if message.author.bot and random.random() < 0.01:
            log.debug("ignoring bot message from %s (5%% skip)", message.author)
            return

        if not message.content.strip() and not message.attachments:
            return

        if not _should_handle(message):
            return

        await _process_message(message)

    return bot


# Backward compatibility: default bot instance (created lazily in main.py)
bot: discord.Client | None = None
