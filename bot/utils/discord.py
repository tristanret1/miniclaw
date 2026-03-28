"""Discord message utilities."""
from bot.constants import DISCORD_MAX_MESSAGE_LENGTH


async def send_chunks(
    channel,
    text: str,
    chunk_size: int = DISCORD_MAX_MESSAGE_LENGTH,
) -> None:
    """Send a long message as multiple chunks to a Discord channel."""
    for i in range(0, len(text), chunk_size):
        await channel.send(text[i : i + chunk_size])
