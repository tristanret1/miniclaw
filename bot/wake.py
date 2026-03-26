"""Wake word gate — detects wake words at the start of STT transcriptions.

Returns the command portion (text after the wake word) if a wake word is found,
or None if no wake word is detected.
"""

from __future__ import annotations

from bot.config import WAKE_WORDS as DEFAULT_WAKE_WORDS


def check(text: str, *, wake_words: list[str] | None = None) -> str | None:
    """Check if text starts with a wake word.

    Returns the command text after the wake word (stripped), or None if
    no wake word is found. Wake word must appear at the start of the text.
    """
    if not text:
        return None

    words = wake_words or DEFAULT_WAKE_WORDS
    text_lower = text.lower().strip()

    for word in words:
        wl = word.lower()
        if not text_lower.startswith(wl):
            continue
        # Extract everything after the wake word (preserve original casing)
        rest_full = text.strip()[len(wl):]
        # Strip leading punctuation/whitespace that STT might add
        rest_full = rest_full.lstrip(" ,，:：、.。!！?？")
        return rest_full.strip()

    return None
