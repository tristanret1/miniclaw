import asyncio
import random
from datetime import datetime

import discord
from bot import llm
from bot.agent import Agent
from bot.message import build_user_content
from bot.config import (
    AUTO_REPLY_ENABLED, AUTO_REPLY_CHANNELS, AUTO_REPLY_CHANCE, AUTO_REPLY_KEYWORDS,
    HEARTBEAT_ENABLED, HEARTBEAT_INTERVAL, HEARTBEAT_CHANNEL_ID,
    HEARTBEAT_ACTIVE_START, HEARTBEAT_ACTIVE_END, HEARTBEAT_ACTIVE_TZ,
    HEARTBEAT_ACK_MAX_CHARS, HEARTBEAT_ISOLATED,
    get_loaded_skills,
)
from bot.skills import match_skill_command, build_skill_user_message, build_skill_command_list
from bot import memory
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
    if not AUTO_REPLY_ENABLED:
        return False
    if message.guild is None:
        return False
    if bot_user in message.mentions:
        return False
    if AUTO_REPLY_CHANNELS and AUTO_REPLY_CHANNELS != ['']:
        if str(message.channel.id) not in AUTO_REPLY_CHANNELS:
            return False
    if AUTO_REPLY_KEYWORDS and AUTO_REPLY_KEYWORDS != ['']:
        content_lower = message.content.lower()
        keyword_triggered = any(keyword.strip().lower() in content_lower
                              for keyword in AUTO_REPLY_KEYWORDS if keyword.strip())
        if not keyword_triggered:
            return False
    return random.random() < AUTO_REPLY_CHANCE


GREETING_CHANNEL_ID = 1482258781860532344


async def _send_greeting(bot: discord.Client, agent: Agent) -> None:
    """Send a startup greeting to the designated channel."""
    try:
        channel = bot.get_channel(GREETING_CHANNEL_ID)
        if channel is None:
            channel = await bot.fetch_channel(GREETING_CHANNEL_ID)

        session_key = f"{GREETING_CHANNEL_ID}:system"
        greeting = await llm.reply(session_key, "你刚刚上线了，用一句话跟大家打个招呼吧", agent=agent)
        await channel.send(greeting[:2000])
        log.info("startup greeting sent to channel %s", GREETING_CHANNEL_ID)
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
        if AUTO_REPLY_ENABLED:
            print(f"Auto-reply enabled with {AUTO_REPLY_CHANCE*100}% chance")

        # Send startup greeting
        await _send_greeting(bot, agent)

        # Start cron scheduler only once (first agent)
        if not _cron_started:
            from bot.config import CRON_ENABLED
            if CRON_ENABLED:
                from bot.cron import get_scheduler
                scheduler = get_scheduler()
                await scheduler.start(bot)
                print("Cron scheduler started")
            _cron_started = True

        # Start heartbeat for this agent
        if HEARTBEAT_ENABLED and agent.name not in _heartbeat_runners:
            channel_id = HEARTBEAT_CHANNEL_ID
            if channel_id:
                from bot.heartbeat import HeartbeatRunner

                async def _deliver_heartbeat(text: str, _bot=bot, _cid=channel_id) -> None:
                    """Deliver heartbeat message to configured Discord channel."""
                    try:
                        channel = _bot.get_channel(int(_cid))
                        if channel is None:
                            channel = await _bot.fetch_channel(int(_cid))
                        for i in range(0, len(text), 2000):
                            await channel.send(text[i : i + 2000])
                    except Exception as e:
                        log.error("heartbeat delivery to channel %s failed: %s", _cid, e)
                        raise

                runner = HeartbeatRunner(
                    agent=agent,
                    deliver_fn=_deliver_heartbeat,
                    interval=HEARTBEAT_INTERVAL,
                    active_hours_start=HEARTBEAT_ACTIVE_START,
                    active_hours_end=HEARTBEAT_ACTIVE_END,
                    active_hours_tz=HEARTBEAT_ACTIVE_TZ,
                    ack_max_chars=HEARTBEAT_ACK_MAX_CHARS,
                    isolated_session=HEARTBEAT_ISOLATED,
                )
                await runner.start()
                _heartbeat_runners[agent.name] = runner
                print(f"Heartbeat started for agent '{agent.name}' (every {HEARTBEAT_INTERVAL})")
            else:
                log.warning("HEARTBEAT_ENABLED but HEARTBEAT_CHANNEL_ID not set — skipping")

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
                for i in range(2000, len(buffer), 2000):
                    await message.channel.send(buffer[i : i + 2000])
        elif buffer.strip():
            for i in range(0, len(buffer), 2000):
                await message.reply(buffer[i : i + 2000])
        else:
            await message.reply("[No response]")

    def _should_handle(message: discord.Message) -> bool:
        if message.guild is not None:
            return bot.user in message.mentions
        return True  # DM

    def _extract_content(message: discord.Message) -> str:
        content = message.content
        if message.guild is not None:
            for mention_str in [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]:
                content = content.replace(mention_str, "").strip()
        return content

    async def _process_message(message: discord.Message) -> None:
        content = _extract_content(message)
        image_urls = _extract_image_urls(message)

        if not content and not image_urls:
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

        session_key = f"{message.channel.id}:{message.author.id}"
        user_content = build_user_content(content, image_urls if image_urls else None)

        if image_urls:
            log.info("multimodal message: %d image(s) + %d chars text", len(image_urls), len(content))

        async with message.channel.typing():
            try:
                reply_text = await llm.reply(session_key, user_content, agent=agent)
                for i in range(0, len(reply_text), 2000):
                    await message.reply(reply_text[i : i + 2000])
            except Exception as e:
                log.error("reply error: %s", e)
                await message.reply(f"Error: {e}")

    @bot.event
    async def on_message(message: discord.Message):
        if message.author == bot.user:
            return

        if not _should_handle(message):
            return

        await _process_message(message)

    return bot


# Backward compatibility: default bot instance (created lazily in main.py)
bot: discord.Client | None = None
