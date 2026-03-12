import asyncio
import random

import discord
from bot.claude import build_user_content, get_reply, get_reply_stream
from bot.config import AUTO_REPLY_ENABLED, AUTO_REPLY_CHANNELS, AUTO_REPLY_CHANCE, AUTO_REPLY_KEYWORDS
from bot.logger import get_logger

log = get_logger("client")

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)

# Supported image MIME types for Claude vision
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

# Streaming: flush interval and buffer
_STREAM_FLUSH_INTERVAL = 1.0  # seconds between Discord edits
_STREAM_FLUSH_CHARS = 200     # min chars accumulated before edit


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
    # Track all sent messages for multi-message replies
    sent_messages: list[discord.Message] = []

    async for chunk in get_reply_stream(session_key, user_content):
        buffer += chunk

        now = asyncio.get_event_loop().time()
        should_edit = (
            (now - last_edit >= _STREAM_FLUSH_INTERVAL and len(buffer) - (len(sent_msg.content) if sent_msg else 0) >= _STREAM_FLUSH_CHARS)
            or len(buffer) > 1900  # approaching Discord limit
        )

        if not sent_msg and buffer.strip():
            # Send initial message
            display = buffer[:2000]
            sent_msg = await message.reply(display + " ▍")
            sent_messages.append(sent_msg)
            last_edit = now

        elif should_edit and sent_msg:
            if len(buffer) > 1900:
                # Finalize current message, start new one
                current_chunk = buffer[:2000]
                await sent_msg.edit(content=current_chunk)
                buffer = buffer[2000:]
                if buffer.strip():
                    sent_msg = await message.channel.send(buffer[:2000] + " ▍")
                    sent_messages.append(sent_msg)
                else:
                    sent_msg = None
            else:
                await sent_msg.edit(content=buffer + " ▍")
            last_edit = now

    # Final edit: remove cursor
    if sent_msg and buffer:
        # Handle remaining buffer that might exceed 2000
        remaining = buffer if not sent_messages else buffer
        if len(remaining) > 2000:
            if sent_msg:
                await sent_msg.edit(content=remaining[:2000])
            for i in range(2000, len(remaining), 2000):
                await message.channel.send(remaining[i:i+2000])
        elif sent_msg:
            await sent_msg.edit(content=remaining[:2000])
    elif not sent_msg and not buffer.strip():
        await message.reply("[No response]")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

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
