"""TTS provider — Volcengine primary, OpenAI + edge-tts fallback.

Supports both batch (returns MP3 bytes) and streaming (yields raw audio chunks)
modes. Streaming uses HTTP chunked transfer for low-latency playback.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator

import edge_tts
import httpx
from openai import AsyncOpenAI

from bot.config import get_config, get_secrets
from bot.logger import get_logger

log = get_logger("tts")

# Lazy singletons — created on first use
_openai_client: AsyncOpenAI | None = None
_httpx_client: httpx.AsyncClient | None = None

# OpenAI streaming TTS outputs raw PCM at 24kHz, 16-bit, mono
STREAM_SAMPLE_RATE = 24000
STREAM_CHUNK_SIZE = 4096  # bytes per chunk from API

# Volcengine TTS endpoint
_VOLCENGINE_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=get_secrets()["OPENAI_API_KEY"])
    return _openai_client


def _get_httpx_client() -> httpx.AsyncClient:
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
    return _httpx_client


def _volcengine_request_body(text: str, *, fmt: str = "mp3") -> dict:
    """Build Volcengine TTS request body."""
    return {
        "req_params": {
            "text": text,
            "speaker": get_config().gateway.volcengine.tts_speaker,
            "additions": json.dumps({
                "disable_markdown_filter": True,
                "enable_language_detector": True,
                "enable_latex_tn": True,
                "disable_default_bit_rate": True,
                "max_length_to_filter_parenthesis": 0,
                "cache_config": {"text_type": 1, "use_cache": True},
            }),
            "audio_params": {
                "format": fmt,
                "sample_rate": STREAM_SAMPLE_RATE,
            },
        },
    }


def _volcengine_headers() -> dict[str, str]:
    return {
        "x-api-key": get_secrets()["VOLCENGINE_TTS_API_KEY"],
        "X-Api-Resource-Id": get_config().gateway.volcengine.tts_resource_id,
        "Content-Type": "application/json",
        "Connection": "keep-alive",
    }


# ── Batch (full audio) ────────────────────────────────────────────────────────


async def synthesize_volcengine(text: str) -> bytes:
    """Synthesize speech using Volcengine TTS (HTTP chunked). Returns MP3 bytes.

    Response is chunked JSON lines: {"code":0, "data":"<base64_audio>"}
    Last chunk has code=20000000 (end signal).
    """
    audio_parts: list[bytes] = []
    async for chunk in stream_volcengine(text):
        audio_parts.append(chunk)
    return b"".join(audio_parts)


async def synthesize_openai(
    text: str,
    *,
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    voice: str | None = None,
) -> bytes:
    """Synthesize speech using OpenAI TTS API. Returns MP3 bytes."""
    c = client or _get_openai_client()
    _voice_cfg = get_config().gateway.voice
    response = await c.audio.speech.create(
        model=model or _voice_cfg.tts_model,
        voice=voice or _voice_cfg.tts_voice,
        input=text,
        speed=_voice_cfg.tts_speed,
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

    Provider priority: volcengine → openai → edge (fallback on failure).
    """
    prov = provider or "volcengine"

    if prov == "volcengine":
        try:
            return await synthesize_volcengine(text)
        except Exception as e:
            log.warning("Volcengine TTS failed, falling back to openai: %s", e)
            prov = "openai"  # fall through

    if prov == "openai":
        try:
            return await synthesize_openai(text)
        except Exception as e:
            log.warning("OpenAI TTS failed, falling back to edge-tts: %s", e)
            return await synthesize_edge(text)

    if prov == "edge":
        return await synthesize_edge(text)

    raise ValueError(f"Unknown TTS provider: {prov}")


# ── Streaming (audio chunks) ─────────────────────────────────────────────────


async def stream_volcengine(text: str) -> AsyncIterator[bytes]:
    """Stream TTS as decoded MP3 chunks from Volcengine HTTP chunked API.

    Response is chunked JSON lines: {"code":0, "data":"<base64_mp3>"}
    Last chunk has code=20000000 (end signal, no audio data).
    Yields decoded MP3 bytes per chunk.
    """
    client = _get_httpx_client()
    async with client.stream(
        "POST",
        _VOLCENGINE_TTS_URL,
        headers=_volcengine_headers(),
        json=_volcengine_request_body(text, fmt="mp3"),
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            code = obj.get("code", 0)
            if code == 20000000:
                break  # end signal
            if code != 0:
                raise RuntimeError(f"Volcengine TTS error: code={code}, message={obj.get('message', '')}")
            data = obj.get("data", "")
            if data:
                yield base64.b64decode(data)


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
    _voice_cfg = get_config().gateway.voice
    async with c.audio.speech.with_streaming_response.create(
        model=model or _voice_cfg.tts_model,
        voice=voice or _voice_cfg.tts_voice,
        input=text,
        speed=_voice_cfg.tts_speed,
        response_format="pcm",
    ) as response:
        async for chunk in response.iter_bytes(chunk_size=STREAM_CHUNK_SIZE):
            yield chunk


async def stream_pcm(text: str, *, provider: str | None = None) -> AsyncIterator[bytes]:
    """Stream TTS as audio chunks.

    Volcengine streams MP3 chunks; OpenAI streams raw PCM (24kHz, 16-bit, mono).
    Falls back to batch synthesis if streaming is unavailable.
    """
    prov = provider or "volcengine"

    if prov == "volcengine":
        try:
            async for chunk in stream_volcengine(text):
                yield chunk
            return
        except Exception as e:
            log.warning("Volcengine streaming TTS failed, falling back to openai: %s", e)
            prov = "openai"

    if prov == "openai":
        try:
            async for chunk in stream_openai(text):
                yield chunk
            return
        except Exception as e:
            log.warning("OpenAI streaming TTS failed: %s", e)

    # Fallback: batch synthesize then yield as single chunk
    log.debug("Falling back to batch TTS")
    mp3_bytes = await synthesize(text, provider=prov)
    yield mp3_bytes
