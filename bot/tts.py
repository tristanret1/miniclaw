"""TTS provider — OpenAI TTS primary, edge-tts fallback.

Produces MP3 audio bytes from text. Used by the voice gateway to speak
responses through the local speakers.
"""

from __future__ import annotations

import edge_tts
from openai import AsyncOpenAI

from bot.config import OPENAI_API_KEY, TTS_MODEL, TTS_SPEED, TTS_VOICE
from bot.logger import get_logger

log = get_logger("tts")

# Lazy singleton — created on first use
_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


async def synthesize_openai(
    text: str,
    *,
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    voice: str | None = None,
) -> bytes:
    """Synthesize speech using OpenAI TTS API. Returns MP3 bytes."""
    c = client or _get_openai_client()
    response = await c.audio.speech.create(
        model=model or TTS_MODEL,
        voice=voice or TTS_VOICE,
        input=text,
        speed=TTS_SPEED,
        response_format="mp3",
    )
    return response.content


async def synthesize_edge(text: str, *, voice: str = "en-US-AriaNeural") -> bytes:
    """Synthesize speech using Microsoft Edge TTS (free, no API key). Returns MP3 bytes."""
    communicate = edge_tts.Communicate(text, voice)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


async def synthesize(text: str, *, provider: str | None = None) -> bytes:
    """Synthesize speech with fallback. Returns MP3 audio bytes.

    Provider priority: openai → edge (fallback on failure).
    """
    prov = provider or "openai"

    if prov == "openai":
        try:
            return await synthesize_openai(text)
        except Exception as e:
            log.warning("OpenAI TTS failed, falling back to edge-tts: %s", e)
            return await synthesize_edge(text)

    if prov == "edge":
        return await synthesize_edge(text)

    raise ValueError(f"Unknown TTS provider: {prov}")
