"""STT provider — OpenAI Whisper API.

Transcribes raw PCM audio bytes to text. Used by the voice gateway
to convert microphone input into text for wake word detection and LLM input.
"""

from __future__ import annotations

import io
import wave

from openai import AsyncOpenAI

from bot.config import OPENAI_API_KEY, STT_MODEL, STT_LANGUAGE, STT_PROMPT, VOICE_SAMPLE_RATE
from bot.logger import get_logger

log = get_logger("stt")

_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw PCM bytes in a WAV container for the Whisper API."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


async def transcribe(
    audio_bytes: bytes,
    *,
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    language: str | None = None,
    sample_rate: int | None = None,
) -> str:
    """Transcribe PCM audio bytes to text using OpenAI Whisper.

    Returns empty string for empty input or on error.
    """
    if not audio_bytes:
        return ""

    # Skip very short audio (< 0.5s) — likely noise, not speech
    sr = sample_rate or VOICE_SAMPLE_RATE
    min_samples = int(sr * 0.5)  # 0.5 seconds
    n_samples = len(audio_bytes) // 2  # 16-bit = 2 bytes per sample
    if n_samples < min_samples:
        log.debug("audio too short (%d samples, need %d), skipping", n_samples, min_samples)
        return ""

    c = client or _get_openai_client()
    wav_bytes = _pcm_to_wav(audio_bytes, sample_rate=sr)

    try:
        kwargs: dict = {
            "model": model or STT_MODEL,
            "file": ("audio.wav", wav_bytes, "audio/wav"),
            "temperature": 0,  # conservative transcription, reduce hallucinations
        }
        lang = language or STT_LANGUAGE
        if lang:
            kwargs["language"] = lang
        if STT_PROMPT:
            kwargs["prompt"] = STT_PROMPT
        transcription = await c.audio.transcriptions.create(**kwargs)
        text = transcription.text.strip()
        if text:
            log.debug("STT: %s", text[:200])
        return text
    except Exception as e:
        log.error("Whisper transcription failed: %s", e)
        return ""
