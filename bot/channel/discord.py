"""Discord channel adapter — transport only."""

import asyncio
from datetime import datetime

import discord

from bot.channel import ChannelAdapter, InboundMessage
from bot.config import get_config, get_loaded_skills
from bot.logger import get_logger
from bot.skills import match_skill_command, build_skill_user_message, build_skill_command_list
from bot.storage import memory
from bot.utils.discord import send_chunks
from bot.utils.session_keys import discord_key

log = get_logger("discord")

_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

# Streaming config
_STREAM_FLUSH_INTERVAL = 0.1
_STREAM_FLUSH_CHARS = 50

# User memory cache: {user_id: (username, display_name)}
_known_users: dict[int, tuple[str, str]] = {}


def _extract_image_urls(message: discord.Message) -> list[str]:
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


class DiscordAdapter(ChannelAdapter):
    """Discord channel adapter with streaming support."""

    name = "discord"
    supports_streaming = True

    def __init__(self, agent):
        self._agent = agent
        self._bot: discord.Client | None = None
        self._gateway = None

    async def start(self, gateway) -> None:
        self._gateway = gateway
        intents = discord.Intents.default()
        intents.message_content = True
        self._bot = discord.Client(intents=intents)
        self._setup_events()

    async def stop(self) -> None:
        if self._bot:
            await self._bot.close()

    async def send(self, reply_ctx: dict, text: str) -> str:
        """Send a complete reply to Discord."""
        message: discord.Message | None = reply_ctx.get("message")
        if not message:
            return "Error: no message in reply_ctx"
        try:
            for i in range(0, len(text), 2000):
                await message.reply(text[i : i + 2000])
            return "ok"
        except Exception as e:
            log.error("discord send error: %s", e)
            return f"Error: {e}"

    async def send_chunk(self, reply_ctx: dict, chunk: str, done: bool) -> None:
        """Stream reply with progressive Discord message editing."""
        state = reply_ctx.setdefault("_stream_state", {
            "buffer": "",
            "sent_msg": None,
            "last_edit": 0.0,
            "last_edit_len": 0,
            "start": asyncio.get_event_loop().time(),
        })
        message: discord.Message = reply_ctx["message"]

        if done:
            # Final: remove cursor, handle overflow
            buf = state["buffer"]
            sent = state["sent_msg"]
            if sent:
                if len(buf) <= 2000:
                    await sent.edit(content=buf)
                else:
                    await sent.edit(content=buf[:2000])
                    await send_chunks(message.channel, buf[2000:])
            elif buf.strip():
                for i in range(0, len(buf), 2000):
                    await message.reply(buf[i : i + 2000])
            else:
                await message.reply("[No response]")
            return

        state["buffer"] += chunk
        buf = state["buffer"]
        now = asyncio.get_event_loop().time()
        sent = state["sent_msg"]

        if not sent:
            if len(buf.strip()) >= 5 or (now - state["start"]) >= 0.3:
                state["sent_msg"] = await message.reply(buf[:1990] + " ▍")
                state["last_edit_len"] = len(buf)
                state["last_edit"] = now
        else:
            new_chars = len(buf) - state["last_edit_len"]
            should_edit = (
                (now - state["last_edit"] >= _STREAM_FLUSH_INTERVAL and new_chars >= _STREAM_FLUSH_CHARS)
                or new_chars >= 100
            )
            if should_edit:
                await sent.edit(content=buf[:1990] + " ▍")
                state["last_edit_len"] = len(buf)
                state["last_edit"] = now

    async def run(self, token: str) -> None:
        """Start the Discord bot and run until cancelled."""
        await self._bot.start(token)

    def _setup_events(self):
        bot = self._bot
        agent = self._agent

        @bot.event
        async def on_ready():
            print(f"Agent '{agent.name}' online as {bot.user}")

        @bot.event
        async def on_message(message: discord.Message):
            if message.author == bot.user:
                return
            if not message.content.strip() and not message.attachments:
                return
            if not self._should_handle(message):
                return

            await self._remember_user(message)
            await self._process_message(message)

    def _should_handle(self, message: discord.Message) -> bool:
        if message.guild is not None:
            return self._bot.user in message.mentions
        allowed = get_config().discord.allowed_dm_users
        if not allowed or message.author.id not in allowed:
            return False
        return True

    def _extract_content(self, message: discord.Message) -> str:
        content = message.content
        if message.guild is not None:
            for mention_str in [f"<@{self._bot.user.id}>", f"<@!{self._bot.user.id}>"]:
                content = content.replace(mention_str, "").strip()
        return content

    async def _remember_user(self, message: discord.Message) -> None:
        user = message.author
        uid = user.id
        username = str(user)
        display_name = user.display_name

        cached = _known_users.get(uid)
        if cached and cached == (username, display_name):
            return
        _known_users[uid] = (username, display_name)

        content = (
            f"用户信息: ID={uid}, 用户名={username}, "
            f"显示名={display_name}, 频道={message.channel.id}, "
            f"时间={datetime.now().isoformat(timespec='seconds')}"
        )
        try:
            await memory.save(content=content, tags=["user_profile"], source="system",
                              memory_dir=self._agent.memory_dir, agent_name=self._agent.name)
        except Exception as e:
            log.error("failed to save user memory for %s: %s", username, e)

    async def _process_message(self, message: discord.Message) -> None:
        content = self._extract_content(message)
        image_urls = _extract_image_urls(message)

        if not content.strip() and not image_urls:
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

        # Prepend sender metadata
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(get_config().services.cron.timezone)
        local_time = message.created_at.astimezone(tz)
        timestamp = local_time.strftime("%Y-%m-%d %H:%M %Z")
        channel_name = getattr(message.channel, "name", "DM")
        meta = f"[{message.author.display_name} (ID:{message.author.id}) · #{channel_name} · {timestamp}]\n"
        content = meta + content

        msg = InboundMessage(
            channel="discord",
            session_key=discord_key(message.channel.id, message.author.id),
            text=content,
            image_urls=image_urls,
            reply_ctx={"message": message},
        )

        from bot import hooks
        hooks.fire_working(self._agent.name, f"Replying in #{channel_name}")
        try:
            async with message.channel.typing():
                await self._gateway.handle(msg)
        except Exception as e:
            log.error("reply error: %s", e)
            await message.reply(f"Error: {e}")
        finally:
            hooks.fire_idle(self._agent.name)
