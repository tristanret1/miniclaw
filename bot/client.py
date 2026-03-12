import asyncio
import random
from datetime import datetime

import discord
from bot.claude import build_user_content, get_reply, get_reply_stream
from bot.config import AUTO_REPLY_ENABLED, AUTO_REPLY_CHANNELS, AUTO_REPLY_CHANCE, AUTO_REPLY_KEYWORDS
from bot import memory
from bot.logger import get_logger

log = get_logger("client")

# ── User memory cache ────────────────────────────────────────────────────────
# Tracks {user_id: (username, display_name)} to avoid duplicate saves
_known_users: dict[int, tuple[str, str]] = {}


async def _remember_user(message: discord.Message) -> None:
    """Save user info to memory if new or name changed."""
    user = message.author
    uid = user.id
    username = str(user)           # e.g. "alice#0" or "alice"
    display_name = user.display_name  # server nickname or global display name

    cached = _known_users.get(uid)
    if cached and cached == (username, display_name):
        return  # no change, skip

    _known_users[uid] = (username, display_name)

    channel_id = message.channel.id
    timestamp = datetime.now().isoformat(timespec="seconds")
    content = (
        f"用户信息: ID={uid}, 用户名={username}, "
        f"显示名={display_name}, 频道={channel_id}, 时间={timestamp}"
    )
    tags = ["user_profile"]

    try:
        result = memory.save(content=content, tags=tags, source="system")
        action = "updated" if cached else "recorded"
        log.info("user memory %s: %s (%s) → %s", action, username, display_name, result)
    except Exception as e:
        log.error("failed to save user memory for %s: %s", username, e)

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)

# Supported image MIME types for Claude vision
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

# Streaming: flush interval and buffer
_STREAM_FLUSH_INTERVAL = 0.3  # seconds between Discord edits
_STREAM_FLUSH_CHARS = 50     # min chars accumulated before edit


@bot.event
async def on_ready():
    print(f"MiniClaw online as {bot.user}")
    if AUTO_REPLY_ENABLED:
        print(f"Auto-reply enabled with {AUTO_REPLY_CHANCE*100}% chance")
        if AUTO_REPLY_CHANNELS:
            print(f"Auto-reply channels: {AUTO_REPLY_CHANNELS}")
        if AUTO_REPLY_KEYWORDS:
            print(f"Auto-reply keywords: {AUTO_REPLY_KEYWORDS}")


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


def should_auto_reply(message: discord.Message) -> bool:
    if not AUTO_REPLY_ENABLED:
        return False
    if message.guild is None:
        return False
    if bot.user in message.mentions:
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


async def _send_streaming(message: discord.Message, session_key: str, user_content):
    """Stream Claude's reply, editing a Discord message progressively."""
    buffer = ""
    sent_msg: discord.Message | None = None
    last_edit = 0.0
    stream_start = asyncio.get_event_loop().time()

    async for chunk in get_reply_stream(session_key, user_content):
        buffer += chunk
        now = asyncio.get_event_loop().time()

        if not sent_msg:
            # Send first message quickly: ≥5 chars OR 0.3s since stream started
            if len(buffer.strip()) >= 5 or (now - stream_start) >= 0.3:
                display = buffer[:1990]  # Leave room for cursor
                sent_msg = await message.reply(display + " ▍")
                last_edit = now
        else:
            # Only update if enough time passed or significant content added
            should_edit = (
                (now - last_edit >= _STREAM_FLUSH_INTERVAL) 
                or (len(buffer) - len(buffer.strip()[:1990]) >= _STREAM_FLUSH_CHARS)
            )

            if should_edit:
                # Always edit the same message, truncate if too long
                display = buffer[:1990]  # Leave room for cursor
                await sent_msg.edit(content=display + " ▍")
                last_edit = now

    # Final edit: remove cursor and show full content (truncated if needed)
    if sent_msg:
        final_content = buffer[:2000]  # Discord limit
        if len(buffer) > 2000:
            final_content = buffer[:1990] + "\n[消息过长，已截断]"
        await sent_msg.edit(content=final_content)
    elif buffer.strip():
        # If no message was sent yet, send it now
        final_content = buffer[:2000]
        if len(buffer) > 2000:
            final_content = buffer[:1990] + "\n[消息过长，已截断]"
        await message.reply(final_content)
    else:
        await message.reply("[No response]")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    # Record user info to memory (non-blocking)
    try:
        await _remember_user(message)
    except Exception as e:
        log.error("user memory error: %s", e)

    # Auto-reply path (non-streaming)
    if should_auto_reply(message):
        session_key = f"{message.channel.id}:{message.author.id}"
        async with message.channel.typing():
            try:
                auto_reply_prompt = f"[自动回复模式] 用户消息: {message.content}"
                reply = await get_reply(session_key, auto_reply_prompt)
                for i in range(0, len(reply), 2000):
                    await message.reply(reply[i : i + 2000])
            except Exception as e:
                log.error("Auto-reply error: %s", e)
        return

    # DM or @mention path
    if message.guild is not None:
        if bot.user not in message.mentions:
            return
        content = message.content
        for mention_str in [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]:
            content = content.replace(mention_str, "").strip()
    else:
        content = message.content

    # Extract images from attachments
    image_urls = _extract_image_urls(message)

    if not content and not image_urls:
        return

    session_key = f"{message.channel.id}:{message.author.id}"
    user_content = build_user_content(content, image_urls if image_urls else None)

    if image_urls:
        log.info("multimodal message: %d image(s) + %d chars text", len(image_urls), len(content))

    try:
        await _send_streaming(message, session_key, user_content)
    except Exception as e:
        log.error("reply error: %s", e)
        await message.reply(f"Error: {e}")
