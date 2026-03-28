"""discord_send tool — send messages to Discord channels."""

from bot.logger import get_logger
from bot.utils.discord import send_chunks

log = get_logger("tools")

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
        num_chunks = (len(message) + 1999) // 2000
        await send_chunks(channel, message)
        log.info("discord_send ✓ sent %d chunk(s) to channel %s", num_chunks, channel_id)
        return f"Message sent to channel {channel_id} ({num_chunks} part(s))."
    except Exception as e:
        log.error("discord_send ✗ failed to send to channel %s: %s", channel_id, e)
        return f"Error sending message: {e}"
