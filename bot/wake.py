"""Wake word gate — detects wake words in STT transcriptions.

Returns the command portion (text after the wake word) if a wake word is found,
or None if no wake word is detected.
"""

from __future__ import annotations

from bot.config import get_config


def check(text: str, *, wake_words: list[str] | None = None) -> str | None:
    """Check if text contains a wake word.

    Searches for the wake word anywhere in the text (not just the start),
    since spoken language often has greetings or filler before the wake word.
    E.g., "嗨，平平，下午好" or "hey peter what time is it"

    Returns the command text after the wake word (stripped), or None if
    no wake word is found.
    """
    if not text:
        return None

    words = wake_words or get_config().gateway.voice.wake_words
    text_lower = text.lower().strip()

    for word in words:
        wl = word.lower()
        pos = text_lower.find(wl)
        if pos == -1:
            continue
        # Extract everything after the wake word (preserve original casing)
        rest_full = text.strip()[pos + len(wl):]
        # Strip leading punctuation/whitespace that STT might add
        rest_full = rest_full.lstrip(" ,，:：、.。!！?？")
        return rest_full.strip()

    return None
