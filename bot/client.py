import asyncio
import random
from datetime import datetime

import discord
from bot import llm
from bot.message import build_user_content
from bot.config import AUTO_REPLY_ENABLED, AUTO_REPLY_CHANNELS, AUTO_REPLY_CHANCE, AUTO_REPLY_KEYWORDS
from bot import memory
from bot.logger import get_logger

log = get_logger("client")

# ── Message debounce ─────────────────────────────────────────────────────────
# Wait for edits before processing. Key: message.id → asyncio.Task
_MSG_DEBOUNCE_DELAY = 1.5  # seconds to wait for edits
_pending_replies: dict[int, asyncio.Task] = {}

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
_STREAM_FLUSH_INTERVAL = 0.1  # seconds between Discord edits
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
    """Stream Claude's reply, editing a single Discord message progressively.

    Strategy: always edit the SAME message during streaming.  Only when the
    final response is complete and exceeds 2 000 chars do we send overflow
    as follow-up messages.
    """
    buffer = ""
    sent_msg: discord.Message | None = None
    last_edit = 0.0
    last_edit_len = 0          # chars that were displayed at the last edit
    stream_start = asyncio.get_event_loop().time()

    async for chunk in llm.stream(session_key, user_content):
        buffer += chunk
        now = asyncio.get_event_loop().time()

        if not sent_msg:
            # Send first message quickly: ≥5 visible chars OR 0.3s elapsed
            if len(buffer.strip()) >= 5 or (now - stream_start) >= 0.3:
                display = buffer[:1990]          # leave room for cursor
                sent_msg = await message.reply(display + " ▍")
                last_edit_len = len(buffer)
                last_edit = now
        else:
            new_chars = len(buffer) - last_edit_len
            should_edit = (
                (now - last_edit >= _STREAM_FLUSH_INTERVAL and new_chars >= _STREAM_FLUSH_CHARS)
                or new_chars >= 100              # force update every 100 new chars
            )

            if should_edit:
                display = buffer[:1990]          # always truncate to Discord limit
                await sent_msg.edit(content=display + " ▍")
                last_edit_len = len(buffer)
                last_edit = now

    # ── Final: remove cursor and send full content ──────────────────────────
    if sent_msg:
        if len(buffer) <= 2000:
            await sent_msg.edit(content=buffer)
        else:
            # First 2000 chars go into the existing message
            await sent_msg.edit(content=buffer[:2000])
            # Overflow → follow-up messages (only once, after stream ends)
            for i in range(2000, len(buffer), 2000):
                await message.channel.send(buffer[i : i + 2000])
    elif buffer.strip():
        # Stream finished before we could send the first message
        for i in range(0, len(buffer), 2000):
            await message.reply(buffer[i : i + 2000])
    else:
        await message.reply("[No response]")


def _should_handle(message: discord.Message) -> bool:
    """Check if this message should be handled (DM or @mention)."""
    if message.guild is not None:
        return bot.user in message.mentions
    return True  # DM


def _extract_content(message: discord.Message) -> str:
    """Extract text content, stripping bot mentions."""
    content = message.content
    if message.guild is not None:
        for mention_str in [f"<@{bot.user.id}>", f"<@!{bot.user.id}>"]:
            content = content.replace(mention_str, "").strip()
    return content


async def _process_message(message: discord.Message) -> None:
    """Process a message after debounce delay (edits settled)."""
    content = _extract_content(message)
    image_urls = _extract_image_urls(message)

    if not content and not image_urls:
        return

    session_key = f"{message.channel.id}:{message.author.id}"
    user_content = build_user_content(content, image_urls if image_urls else None)

    if image_urls:
        log.info("multimodal message: %d image(s) + %d chars text", len(image_urls), len(content))

    async with message.channel.typing():
        try:
            reply_text = await llm.reply(session_key, user_content)
            for i in range(0, len(reply_text), 2000):
                await message.reply(reply_text[i : i + 2000])
        except Exception as e:
            log.error("reply error: %s", e)
            await message.reply(f"Error: {e}")


async def _debounced_reply(message: discord.Message) -> None:
    """Wait for potential edits before processing the message."""
    try:
        await asyncio.sleep(_MSG_DEBOUNCE_DELAY)
        # If we get here, no edit cancelled us — process the message
        await _process_message(message)
    except asyncio.CancelledError:
        log.debug("debounce cancelled for message %d (edited)", message.id)
    finally:
        _pending_replies.pop(message.id, None)


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    # Record user info to memory (non-blocking)
    try:
        await _remember_user(message)
    except Exception as e:
        log.error("user memory error: %s", e)

    # Auto-reply path (no debounce needed)
    if should_auto_reply(message):
        session_key = f"{message.channel.id}:{message.author.id}"
        async with message.channel.typing():
            try:
                auto_reply_prompt = f"[自动回复模式] 用户消息: {message.content}"
                reply_text = await llm.reply(session_key, auto_reply_prompt)
                for i in range(0, len(reply_text), 2000):
                    await message.reply(reply_text[i : i + 2000])
            except Exception as e:
                log.error("Auto-reply error: %s", e)
        return

    # DM or @mention path — debounce to wait for edits
    if not _should_handle(message):
        return

    # Cancel any existing pending reply for this message
    old_task = _pending_replies.pop(message.id, None)
    if old_task:
        old_task.cancel()

    task = asyncio.create_task(_debounced_reply(message))
    _pending_replies[message.id] = task


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """If a pending message is edited, restart the debounce timer."""
    if after.author == bot.user:
        return
    if not _should_handle(after):
        return

    # Only restart if we have a pending (not-yet-processed) reply
    old_task = _pending_replies.pop(after.id, None)
    if old_task:
        old_task.cancel()
        log.info("message %d edited, restarting debounce", after.id)
        task = asyncio.create_task(_debounced_reply(after))
        _pending_replies[after.id] = task
