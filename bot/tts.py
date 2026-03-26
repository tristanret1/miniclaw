"""TTS provider — OpenAI TTS primary, edge-tts fallback.

Supports both batch (returns MP3 bytes) and streaming (yields raw PCM chunks)
modes. Streaming uses OpenAI's PCM output for low-latency playback.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import edge_tts
from openai import AsyncOpenAI

from bot.config import OPENAI_API_KEY, TTS_MODEL, TTS_SPEED, TTS_VOICE
from bot.logger import get_logger

log = get_logger("tts")

# Lazy singleton — created on first use
_openai_client: AsyncOpenAI | None = None

# OpenAI streaming TTS outputs raw PCM at 24kHz, 16-bit, mono
STREAM_SAMPLE_RATE = 24000
STREAM_CHUNK_SIZE = 4096  # bytes per chunk from API


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


# ── Batch (full audio) ────────────────────────────────────────────────────────


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


# ── Streaming (PCM chunks) ───────────────────────────────────────────────────


async def stream_openai(
    text: str,
    *,
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    voice: str | None = None,
) -> AsyncIterator[bytes]:
    """Stream TTS as raw PCM chunks (24kHz, 16-bit, mono).

    Yields chunks as soon as they arrive from the API, enabling
    near-instant playback start.
    """
    c = client or _get_openai_client()
    async with c.audio.speech.with_streaming_response.create(
        model=model or TTS_MODEL,
        voice=voice or TTS_VOICE,
        input=text,
        speed=TTS_SPEED,
        response_format="pcm",
    ) as response:
        async for chunk in response.iter_bytes(chunk_size=STREAM_CHUNK_SIZE):
            yield chunk


async def stream_pcm(text: str, *, provider: str | None = None) -> AsyncIterator[bytes]:
    """Stream TTS as raw PCM chunks (24kHz, 16-bit, mono).

    Falls back to batch synthesis if streaming is unavailable.
    """
    prov = provider or "openai"

    if prov == "openai":
        try:
            async for chunk in stream_openai(text):
                yield chunk
            return
        except Exception as e:
            log.warning("OpenAI streaming TTS failed: %s", e)

    # Fallback: batch synthesize then yield as single chunk
    # (edge-tts doesn't support raw PCM streaming easily)
    log.debug("Falling back to batch TTS")
    mp3_bytes = await synthesize(text, provider=prov)
    yield mp3_bytes
