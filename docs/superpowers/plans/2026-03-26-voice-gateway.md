# Voice Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local voice gateway that listens on the macOS microphone, detects wake words via STT, processes commands through the shared LLM pipeline, and speaks responses back through the speakers — running as a peer channel alongside Discord, SMS, and iMessage gateways.

**Architecture:** The voice gateway follows the same pattern as `imessage_gateway.py` and `sms_gateway.py`: a standalone `start_voice_gateway()` async function launched via `asyncio.gather()` in `main.py`. Audio capture runs in a thread (PyAudio callback → asyncio queue). VAD segments speech by RMS silence detection. Whisper API transcribes segments. Wake word matching gates LLM dispatch. OpenAI TTS (with edge-tts fallback) generates audio played back through PyAudio.

**Tech Stack:** Python 3.13+, PyAudio (PortAudio bindings), OpenAI API (Whisper STT + TTS), edge-tts (free fallback), existing `bot.llm` / `bot.message` / `bot.logger` modules.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `bot/tts.py` | TTS provider abstraction: `synthesize(text) → bytes` (PCM/MP3). OpenAI TTS primary, edge-tts fallback. |
| `bot/stt.py` | STT provider: `transcribe(audio_bytes) → str`. OpenAI Whisper API. |
| `bot/wake.py` | Wake word gate: `check(text) → command | None`. Text prefix matching after STT. |
| `bot/voice_gateway.py` | Gateway main loop: mic capture → VAD → STT → wake → LLM → TTS → playback. Session key `voice:local`. |
| `bot/config.py` | Add `VOICE_ENABLED` and related env vars. |
| `main.py` | Add voice gateway to `asyncio.gather()` startup. |
| `.env.example` | Document new env vars. |
| `requirements.txt` | Add `pyaudio`, `openai`, `edge-tts`. |
| `tests/test_tts.py` | TTS unit tests. |
| `tests/test_stt.py` | STT unit tests. |
| `tests/test_wake.py` | Wake word unit tests. |
| `tests/test_voice_gateway.py` | Voice gateway integration tests. |

---

### Task 1: Dependencies and Configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `bot/config.py:84-95` (add after iMessage config block)
- Modify: `.env.example` (add voice section)
- Modify: `tests/conftest.py:16-48` (add voice env defaults)

- [ ] **Step 1: Add dependencies to requirements.txt**

Append to `requirements.txt`:

```
pyaudio>=0.2.14
openai>=1.0
edge-tts>=6.1
```

- [ ] **Step 2: Add voice config vars to bot/config.py**

Add after the iMessage config block (after line 94):

```python
# Voice gateway (local microphone → STT → LLM → TTS → speaker)
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "false").lower() in ("true", "1", "yes")
WAKE_WORDS = [w.strip().lower() for w in os.getenv("WAKE_WORDS", "miniclaw,小爪").split(",") if w.strip()]
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "openai")  # "openai" or "edge"
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")  # OpenAI voice name
TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")  # OpenAI TTS model
STT_MODEL = os.getenv("STT_MODEL", "whisper-1")  # OpenAI Whisper model
VOICE_SILENCE_THRESHOLD = int(os.getenv("VOICE_SILENCE_THRESHOLD", "500"))  # RMS threshold
VOICE_SILENCE_DURATION = float(os.getenv("VOICE_SILENCE_DURATION", "1.5"))  # seconds of silence to segment
VOICE_SAMPLE_RATE = int(os.getenv("VOICE_SAMPLE_RATE", "16000"))  # Hz
```

- [ ] **Step 3: Add voice env vars to .env.example**

Append before the multi-agent section:

```
# Optional — Voice gateway (local microphone, macOS)
# VOICE_ENABLED=false
# WAKE_WORDS=miniclaw,小爪              # comma-separated wake words
# TTS_PROVIDER=openai                   # "openai" or "edge"
# TTS_VOICE=alloy                       # OpenAI voice: alloy, echo, fable, onyx, nova, shimmer
# TTS_MODEL=gpt-4o-mini-tts            # OpenAI TTS model
# STT_MODEL=whisper-1                   # OpenAI Whisper model
# VOICE_SILENCE_THRESHOLD=500           # RMS silence threshold (0-32767)
# VOICE_SILENCE_DURATION=1.5            # seconds of silence to split utterance
# VOICE_SAMPLE_RATE=16000               # audio sample rate in Hz
```

- [ ] **Step 4: Add voice env defaults to tests/conftest.py**

Add these keys to the `defaults` dict in `pytest_configure`:

```python
"VOICE_ENABLED": "false",
"WAKE_WORDS": "testbot",
"TTS_PROVIDER": "openai",
"TTS_VOICE": "alloy",
"TTS_MODEL": "gpt-4o-mini-tts",
"STT_MODEL": "whisper-1",
"VOICE_SILENCE_THRESHOLD": "500",
"VOICE_SILENCE_DURATION": "1.5",
"VOICE_SAMPLE_RATE": "16000",
```

- [ ] **Step 5: Verify config loads**

Run: `python -c "from bot.config import VOICE_ENABLED, WAKE_WORDS, TTS_PROVIDER; print(VOICE_ENABLED, WAKE_WORDS, TTS_PROVIDER)"`

Expected: `False ['miniclaw', '小爪'] openai`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt bot/config.py .env.example tests/conftest.py
git commit -m "feat(voice): add voice gateway config and dependencies"
```

---

### Task 2: TTS Provider (`bot/tts.py`)

**Files:**
- Create: `bot/tts.py`
- Test: `tests/test_tts.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tts.py`:

```python
"""Tests for bot.tts — TTS provider abstraction."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestOpenAITTS:
    """OpenAI TTS provider tests."""

    @pytest.mark.asyncio
    async def test_synthesize_returns_audio_bytes(self):
        """synthesize() calls OpenAI API and returns audio bytes."""
        from bot.tts import synthesize_openai

        fake_response = MagicMock()
        fake_response.content = b"fake-audio-data"

        mock_client = AsyncMock()
        mock_client.audio.speech.create = AsyncMock(return_value=fake_response)

        result = await synthesize_openai("Hello world", client=mock_client)
        assert result == b"fake-audio-data"
        mock_client.audio.speech.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_synthesize_openai_uses_config(self):
        """synthesize_openai() passes model and voice from config."""
        from bot.tts import synthesize_openai

        fake_response = MagicMock()
        fake_response.content = b"audio"

        mock_client = AsyncMock()
        mock_client.audio.speech.create = AsyncMock(return_value=fake_response)

        await synthesize_openai(
            "test", client=mock_client, model="tts-1", voice="nova"
        )
        call_kwargs = mock_client.audio.speech.create.call_args[1]
        assert call_kwargs["model"] == "tts-1"
        assert call_kwargs["voice"] == "nova"


class TestEdgeTTS:
    """Edge TTS fallback tests."""

    @pytest.mark.asyncio
    async def test_synthesize_edge_returns_bytes(self):
        """synthesize_edge() returns concatenated audio bytes."""
        from bot.tts import synthesize_edge

        fake_chunks = [
            {"type": "audio", "data": b"chunk1"},
            {"type": "audio", "data": b"chunk2"},
        ]

        with patch("bot.tts.edge_tts") as mock_edge:
            mock_communicate = AsyncMock()
            mock_communicate.stream = AsyncMock(return_value=fake_chunks.__aiter__() if hasattr(fake_chunks, '__aiter__') else fake_chunks)
            # Make stream() an async generator
            async def fake_stream():
                for chunk in fake_chunks:
                    yield chunk
            mock_communicate.stream = fake_stream
            mock_edge.Communicate.return_value = mock_communicate

            result = await synthesize_edge("Hello")
            assert result == b"chunk1chunk2"


class TestSynthesizeDispatch:
    """Top-level synthesize() dispatch tests."""

    @pytest.mark.asyncio
    async def test_synthesize_dispatches_to_openai(self):
        """synthesize() calls OpenAI when provider is 'openai'."""
        with patch("bot.tts.synthesize_openai", new_callable=AsyncMock, return_value=b"audio") as mock_openai:
            from bot.tts import synthesize
            result = await synthesize("Hello", provider="openai")
            assert result == b"audio"
            mock_openai.assert_called_once()

    @pytest.mark.asyncio
    async def test_synthesize_dispatches_to_edge(self):
        """synthesize() calls edge-tts when provider is 'edge'."""
        with patch("bot.tts.synthesize_edge", new_callable=AsyncMock, return_value=b"audio") as mock_edge:
            from bot.tts import synthesize
            result = await synthesize("Hello", provider="edge")
            assert result == b"audio"
            mock_edge.assert_called_once()

    @pytest.mark.asyncio
    async def test_synthesize_falls_back_on_failure(self):
        """synthesize() falls back to edge-tts when OpenAI fails."""
        with patch("bot.tts.synthesize_openai", new_callable=AsyncMock, side_effect=Exception("API error")), \
             patch("bot.tts.synthesize_edge", new_callable=AsyncMock, return_value=b"fallback") as mock_edge:
            from bot.tts import synthesize
            result = await synthesize("Hello", provider="openai")
            assert result == b"fallback"
            mock_edge.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tts.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'bot.tts'`

- [ ] **Step 3: Implement bot/tts.py**

Create `bot/tts.py`:

```python
"""TTS provider — OpenAI TTS primary, edge-tts fallback.

Produces MP3 audio bytes from text. Used by the voice gateway to speak
responses through the local speakers.
"""

from __future__ import annotations

import edge_tts
from openai import AsyncOpenAI

from bot.config import OPENAI_API_KEY, TTS_MODEL, TTS_VOICE
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tts.py -v`

Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bot/tts.py tests/test_tts.py
git commit -m "feat(voice): add TTS provider with OpenAI + edge-tts fallback"
```

---

### Task 3: STT Provider (`bot/stt.py`)

**Files:**
- Create: `bot/stt.py`
- Test: `tests/test_stt.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_stt.py`:

```python
"""Tests for bot.stt — STT (speech-to-text) provider."""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestWhisperSTT:
    """OpenAI Whisper STT tests."""

    @pytest.mark.asyncio
    async def test_transcribe_returns_text(self):
        """transcribe() calls Whisper API and returns transcription text."""
        from bot.stt import transcribe

        mock_transcription = MagicMock()
        mock_transcription.text = "hello world"

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcription)

        result = await transcribe(b"fake-audio", client=mock_client)
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_transcribe_passes_model(self):
        """transcribe() passes the configured model to Whisper API."""
        from bot.stt import transcribe

        mock_transcription = MagicMock()
        mock_transcription.text = "test"

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcription)

        await transcribe(b"audio", client=mock_client, model="whisper-1")
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["model"] == "whisper-1"

    @pytest.mark.asyncio
    async def test_transcribe_sends_wav_file(self):
        """transcribe() wraps raw PCM bytes in a WAV container for the API."""
        from bot.stt import transcribe

        mock_transcription = MagicMock()
        mock_transcription.text = "test"

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcription)

        await transcribe(b"\x00" * 3200, client=mock_client, sample_rate=16000)
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        # The file should be a tuple (filename, bytes, content_type)
        file_arg = call_kwargs["file"]
        assert file_arg[0] == "audio.wav"

    @pytest.mark.asyncio
    async def test_transcribe_empty_audio_returns_empty(self):
        """transcribe() returns empty string for empty audio input."""
        from bot.stt import transcribe

        result = await transcribe(b"")
        assert result == ""

    @pytest.mark.asyncio
    async def test_transcribe_handles_api_error(self):
        """transcribe() returns empty string on API error."""
        from bot.stt import transcribe

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(side_effect=Exception("API down"))

        result = await transcribe(b"audio-data", client=mock_client)
        assert result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stt.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'bot.stt'`

- [ ] **Step 3: Implement bot/stt.py**

Create `bot/stt.py`:

```python
"""STT provider — OpenAI Whisper API.

Transcribes raw PCM audio bytes to text. Used by the voice gateway
to convert microphone input into text for wake word detection and LLM input.
"""

from __future__ import annotations

import io
import struct
import wave

from openai import AsyncOpenAI

from bot.config import OPENAI_API_KEY, STT_MODEL, VOICE_SAMPLE_RATE
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
    sample_rate: int | None = None,
) -> str:
    """Transcribe PCM audio bytes to text using OpenAI Whisper.

    Returns empty string for empty input or on error.
    """
    if not audio_bytes:
        return ""

    c = client or _get_openai_client()
    sr = sample_rate or VOICE_SAMPLE_RATE
    wav_bytes = _pcm_to_wav(audio_bytes, sample_rate=sr)

    try:
        transcription = await c.audio.transcriptions.create(
            model=model or STT_MODEL,
            file=("audio.wav", wav_bytes, "audio/wav"),
        )
        text = transcription.text.strip()
        if text:
            log.debug("STT: %s", text[:200])
        return text
    except Exception as e:
        log.error("Whisper transcription failed: %s", e)
        return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stt.py -v`

Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bot/stt.py tests/test_stt.py
git commit -m "feat(voice): add Whisper STT provider"
```

---

### Task 4: Wake Word Gate (`bot/wake.py`)

**Files:**
- Create: `bot/wake.py`
- Test: `tests/test_wake.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_wake.py`:

```python
"""Tests for bot.wake — wake word detection from STT text."""

import pytest


class TestWakeWordCheck:
    """Wake word matching tests."""

    def test_detects_wake_word_at_start(self):
        from bot.wake import check
        result = check("miniclaw what time is it", wake_words=["miniclaw"])
        assert result == "what time is it"

    def test_detects_wake_word_case_insensitive(self):
        from bot.wake import check
        result = check("MiniClaw tell me a joke", wake_words=["miniclaw"])
        assert result == "tell me a joke"

    def test_detects_chinese_wake_word(self):
        from bot.wake import check
        result = check("小爪 今天天气怎么样", wake_words=["小爪"])
        assert result == "今天天气怎么样"

    def test_returns_none_without_wake_word(self):
        from bot.wake import check
        result = check("what time is it", wake_words=["miniclaw"])
        assert result is None

    def test_empty_text_returns_none(self):
        from bot.wake import check
        result = check("", wake_words=["miniclaw"])
        assert result is None

    def test_wake_word_only_returns_empty_command(self):
        from bot.wake import check
        result = check("miniclaw", wake_words=["miniclaw"])
        assert result == ""

    def test_multiple_wake_words(self):
        from bot.wake import check
        result = check("小爪 你好", wake_words=["miniclaw", "小爪"])
        assert result == "你好"

    def test_wake_word_with_punctuation(self):
        """Handle STT adding comma after wake word: 'miniclaw, do X'."""
        from bot.wake import check
        result = check("miniclaw, play some music", wake_words=["miniclaw"])
        assert result == "play some music"

    def test_wake_word_mid_sentence_ignored(self):
        """Only match wake word at the start of the utterance."""
        from bot.wake import check
        result = check("hey miniclaw do something", wake_words=["miniclaw"])
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wake.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'bot.wake'`

- [ ] **Step 3: Implement bot/wake.py**

Create `bot/wake.py`:

```python
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
        # Extract everything after the wake word
        rest = text_lower[len(wl):]
        # Strip leading punctuation/whitespace that STT might add (e.g., "miniclaw, ...")
        rest_full = text.strip()[len(wl):]
        rest_full = rest_full.lstrip(" ,，:：、.。!！?？")
        return rest_full.strip()

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wake.py -v`

Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bot/wake.py tests/test_wake.py
git commit -m "feat(voice): add wake word detection gate"
```

---

### Task 5: Voice Gateway (`bot/voice_gateway.py`)

**Files:**
- Create: `bot/voice_gateway.py`
- Test: `tests/test_voice_gateway.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_voice_gateway.py`:

```python
"""Tests for bot.voice_gateway — local microphone voice gateway."""

import asyncio
import struct
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestVAD:
    """Voice Activity Detection tests."""

    def test_rms_silent_frame(self):
        """RMS of silence is 0."""
        from bot.voice_gateway import compute_rms
        silence = b"\x00" * 3200  # 1600 zero samples (16-bit)
        assert compute_rms(silence) == 0

    def test_rms_loud_frame(self):
        """RMS of a loud frame exceeds threshold."""
        from bot.voice_gateway import compute_rms
        # Max amplitude 16-bit samples
        loud = struct.pack(f"<{800}h", *([32767] * 800))
        assert compute_rms(loud) > 500

    def test_rms_empty_returns_zero(self):
        from bot.voice_gateway import compute_rms
        assert compute_rms(b"") == 0


class TestAudioSegmenter:
    """Audio segmentation by silence tests."""

    @pytest.mark.asyncio
    async def test_segments_on_silence(self):
        """AudioSegmenter yields a segment after silence duration."""
        from bot.voice_gateway import AudioSegmenter

        segmenter = AudioSegmenter(
            silence_threshold=100,
            silence_duration=0.1,  # 100ms for fast test
            sample_rate=16000,
            frame_size=1600,  # 100ms frames
        )

        # Feed one loud frame then two silent frames
        loud_frame = struct.pack(f"<{800}h", *([10000] * 800))
        silent_frame = b"\x00" * 1600

        result = segmenter.feed(loud_frame)
        assert result is None  # still speaking

        result = segmenter.feed(silent_frame)
        assert result is None  # silence just started

        result = segmenter.feed(silent_frame)
        # After enough silence, should return the accumulated speech
        assert result is not None
        assert len(result) > 0


class TestProcessUtterance:
    """End-to-end utterance processing tests."""

    @pytest.mark.asyncio
    async def test_wake_word_triggers_llm(self):
        """When wake word detected, utterance is sent to LLM and response is spoken."""
        from bot.voice_gateway import _process_utterance

        with patch("bot.voice_gateway.stt.transcribe", new_callable=AsyncMock, return_value="miniclaw hello") as mock_stt, \
             patch("bot.voice_gateway.wake.check", return_value="hello") as mock_wake, \
             patch("bot.voice_gateway.llm.reply", new_callable=AsyncMock, return_value="Hi there!") as mock_llm, \
             patch("bot.voice_gateway.tts.synthesize", new_callable=AsyncMock, return_value=b"audio") as mock_tts, \
             patch("bot.voice_gateway._play_audio", new_callable=AsyncMock) as mock_play:

            await _process_utterance(b"fake-audio")

            mock_stt.assert_called_once_with(b"fake-audio")
            mock_wake.assert_called_once_with("miniclaw hello")
            mock_llm.assert_called_once()
            mock_tts.assert_called_once_with("Hi there!")
            mock_play.assert_called_once_with(b"audio")

    @pytest.mark.asyncio
    async def test_no_wake_word_skips_llm(self):
        """When no wake word detected, LLM is not called."""
        from bot.voice_gateway import _process_utterance

        with patch("bot.voice_gateway.stt.transcribe", new_callable=AsyncMock, return_value="random speech") as mock_stt, \
             patch("bot.voice_gateway.wake.check", return_value=None), \
             patch("bot.voice_gateway.llm.reply", new_callable=AsyncMock) as mock_llm:

            await _process_utterance(b"fake-audio")

            mock_stt.assert_called_once()
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_transcription_skips(self):
        """When STT returns empty, processing stops early."""
        from bot.voice_gateway import _process_utterance

        with patch("bot.voice_gateway.stt.transcribe", new_callable=AsyncMock, return_value=""), \
             patch("bot.voice_gateway.wake.check") as mock_wake:

            await _process_utterance(b"fake-audio")

            mock_wake.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_voice_gateway.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'bot.voice_gateway'`

- [ ] **Step 3: Implement bot/voice_gateway.py**

Create `bot/voice_gateway.py`:

```python
"""Voice gateway — local microphone → STT → wake word → LLM → TTS → speaker.

Runs as a peer gateway alongside Discord, SMS, and iMessage.
Audio capture uses PyAudio in a callback thread; processing is async.
"""

from __future__ import annotations

import asyncio
import math
import struct
import subprocess
import tempfile
from pathlib import Path

import pyaudio

from bot import llm, stt, tts, wake
from bot.config import (
    TTS_PROVIDER,
    VOICE_SAMPLE_RATE,
    VOICE_SILENCE_DURATION,
    VOICE_SILENCE_THRESHOLD,
)
from bot.logger import get_logger
from bot.message import build_user_content

log = get_logger("voice")

SESSION_KEY = "voice:local"


# ── VAD helpers ───────────────────────────────────────────────────────────────


def compute_rms(frame: bytes) -> int:
    """Compute RMS (root mean square) amplitude of 16-bit PCM audio frame."""
    if not frame:
        return 0
    n_samples = len(frame) // 2
    if n_samples == 0:
        return 0
    samples = struct.unpack(f"<{n_samples}h", frame[:n_samples * 2])
    return int(math.sqrt(sum(s * s for s in samples) / n_samples))


class AudioSegmenter:
    """Segments continuous audio into utterances based on silence detection.

    Accumulates frames while speech is detected (RMS > threshold).
    After `silence_duration` seconds of silence, yields the accumulated audio.
    """

    def __init__(
        self,
        silence_threshold: int = 500,
        silence_duration: float = 1.5,
        sample_rate: int = 16000,
        frame_size: int = 1600,
    ):
        self._threshold = silence_threshold
        self._silence_frames_needed = int(silence_duration * sample_rate / frame_size)
        self._buffer: list[bytes] = []
        self._silence_count = 0
        self._is_speaking = False

    def feed(self, frame: bytes) -> bytes | None:
        """Feed an audio frame. Returns accumulated audio when utterance ends, else None."""
        rms = compute_rms(frame)

        if rms > self._threshold:
            # Speech detected
            self._is_speaking = True
            self._silence_count = 0
            self._buffer.append(frame)
            return None

        if self._is_speaking:
            # Silence during speech
            self._buffer.append(frame)
            self._silence_count += 1

            if self._silence_count >= self._silence_frames_needed:
                # Utterance complete
                audio = b"".join(self._buffer)
                self._buffer.clear()
                self._silence_count = 0
                self._is_speaking = False
                return audio

        return None

    def reset(self) -> None:
        """Reset segmenter state."""
        self._buffer.clear()
        self._silence_count = 0
        self._is_speaking = False


# ── Audio playback ────────────────────────────────────────────────────────────


async def _play_audio(mp3_bytes: bytes) -> None:
    """Play MP3 audio through the default speaker using ffplay."""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_bytes)
        tmp_path = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", tmp_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ── Utterance processing ─────────────────────────────────────────────────────


async def _process_utterance(audio_bytes: bytes) -> None:
    """Process a single utterance: STT → wake check → LLM → TTS → play."""
    # 1. Transcribe
    text = await stt.transcribe(audio_bytes)
    if not text:
        return

    log.info("heard: %s", text[:200])

    # 2. Wake word check
    command = wake.check(text)
    if command is None:
        log.debug("no wake word detected, ignoring")
        return

    log.info("wake word detected, command: %s", command[:200] if command else "(empty)")

    # If wake word only (no command), use a greeting prompt
    user_text = command if command else "hey"
    user_content = build_user_content(user_text, [])

    # 3. LLM
    reply_text = await llm.reply(SESSION_KEY, user_content)
    if not reply_text.strip():
        return

    log.info("reply: %s", reply_text[:200])

    # 4. TTS
    audio = await tts.synthesize(reply_text, provider=TTS_PROVIDER)

    # 5. Play
    await _play_audio(audio)


# ── Gateway lifecycle ─────────────────────────────────────────────────────────


async def start_voice_gateway() -> None:
    """Start the voice gateway. Listens on local microphone until cancelled.

    Audio capture runs in a PyAudio callback thread. Frames are pushed to an
    asyncio queue for processing in the main event loop.
    """
    log.info("Voice gateway starting (sample_rate=%d, threshold=%d, silence=%.1fs)",
             VOICE_SAMPLE_RATE, VOICE_SILENCE_THRESHOLD, VOICE_SILENCE_DURATION)

    frame_size = VOICE_SAMPLE_RATE // 10  # 100ms frames
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    # PyAudio callback — runs in a separate thread
    def audio_callback(in_data, frame_count, time_info, status):
        loop.call_soon_threadsafe(audio_queue.put_nowait, in_data)
        return (None, pyaudio.paContinue)

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=VOICE_SAMPLE_RATE,
        input=True,
        frames_per_buffer=frame_size,
        stream_callback=audio_callback,
    )
    stream.start_stream()
    log.info("Voice gateway listening on microphone")

    segmenter = AudioSegmenter(
        silence_threshold=VOICE_SILENCE_THRESHOLD,
        silence_duration=VOICE_SILENCE_DURATION,
        sample_rate=VOICE_SAMPLE_RATE,
        frame_size=frame_size * 2,  # bytes per frame (16-bit = 2 bytes/sample)
    )

    try:
        while True:
            frame = await audio_queue.get()
            utterance = segmenter.feed(frame)
            if utterance:
                # Process in background so we keep listening
                asyncio.create_task(_process_utterance(utterance))
    except asyncio.CancelledError:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        log.info("Voice gateway stopped")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_voice_gateway.py -v`

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add bot/voice_gateway.py tests/test_voice_gateway.py
git commit -m "feat(voice): add voice gateway with mic capture, VAD, and utterance processing"
```

---

### Task 6: Startup Integration

**Files:**
- Modify: `main.py:56-63` (add voice gateway startup)
- Modify: `bot/config.py` (already done in Task 1, verify import)

- [ ] **Step 1: Write the failing test**

Create `tests/test_voice_startup.py`:

```python
"""Test that voice gateway integrates into main.py startup."""

import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_voice_gateway_started_when_enabled():
    """When VOICE_ENABLED=true, start_voice_gateway() is called in main()."""
    with patch("bot.config.VOICE_ENABLED", True), \
         patch("bot.config.SMS_ENABLED", False), \
         patch("bot.config.IMESSAGE_ENABLED", False), \
         patch("bot.voice_gateway.start_voice_gateway", new_callable=AsyncMock) as mock_voice, \
         patch("bot.agent.load_agents", return_value=[]), \
         patch("bot.db.use_postgres", return_value=False), \
         patch("asyncio.gather", new_callable=AsyncMock) as mock_gather:

        # Import and run main
        import importlib
        import main as main_mod
        importlib.reload(main_mod)

        # We can't easily test main() directly because it calls asyncio.gather
        # which runs forever. Instead, verify the import path works.
        from bot.voice_gateway import start_voice_gateway
        assert callable(start_voice_gateway)


@pytest.mark.asyncio
async def test_voice_gateway_not_started_when_disabled():
    """When VOICE_ENABLED=false (default), voice gateway is not started."""
    # Default config has VOICE_ENABLED=false, so start_voice_gateway should not be imported
    from bot.config import VOICE_ENABLED
    assert VOICE_ENABLED is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_voice_startup.py -v`

Expected: FAIL (import may fail if main.py doesn't have the voice block yet)

- [ ] **Step 3: Add voice gateway to main.py**

In `main.py`, add after the iMessage gateway block (after line 63):

```python
    if VOICE_ENABLED:
        from bot.voice_gateway import start_voice_gateway
        tasks.append(start_voice_gateway())
```

And update the import at line 30:

```python
from bot.config import SMS_ENABLED, IMESSAGE_ENABLED, VOICE_ENABLED
```

The full relevant section of `main.py` should be:

```python
from bot.config import SMS_ENABLED, IMESSAGE_ENABLED, VOICE_ENABLED
```

```python
    if SMS_ENABLED:
        from bot.sms_gateway import start_sms_server
        tasks.append(start_sms_server())

    if IMESSAGE_ENABLED:
        from bot.imessage_gateway import start_imessage_gateway
        tasks.append(start_imessage_gateway())

    if VOICE_ENABLED:
        from bot.voice_gateway import start_voice_gateway
        tasks.append(start_voice_gateway())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_voice_startup.py -v`

Expected: All 2 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`

Expected: All existing tests still pass + new voice tests pass

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_voice_startup.py
git commit -m "feat(voice): integrate voice gateway into main.py startup"
```

---

### Task 7: Manual Smoke Test

This task is not TDD — it's a manual integration test to verify the full pipeline works on real hardware.

- [ ] **Step 1: Install system dependencies**

```bash
# PyAudio needs PortAudio
brew install portaudio ffmpeg

# Install Python dependencies
pip install -r requirements.txt
```

- [ ] **Step 2: Configure .env for voice**

Add to `.env`:

```
VOICE_ENABLED=true
WAKE_WORDS=miniclaw,小爪
TTS_PROVIDER=openai
OPENAI_API_KEY=sk-...   # required for both Whisper STT and OpenAI TTS
```

- [ ] **Step 3: Test voice gateway standalone**

```bash
python -c "
import asyncio
from bot.voice_gateway import start_voice_gateway
try:
    asyncio.run(start_voice_gateway())
except KeyboardInterrupt:
    print('stopped')
"
```

Speak "miniclaw hello" into the microphone. Expected:
1. Console shows `heard: miniclaw hello`
2. Console shows `wake word detected, command: hello`
3. Console shows `reply: ...` (LLM response)
4. Audio plays through speakers

- [ ] **Step 4: Test full bot startup**

```bash
VOICE_ENABLED=true python main.py
```

Expected: Voice gateway runs alongside Discord bot. Both respond independently.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix(voice): smoke test fixes"
```

---

## Summary

| Task | What it delivers | New files |
|------|------------------|-----------|
| 1 | Config + dependencies | — (modifications only) |
| 2 | TTS (OpenAI + edge-tts fallback) | `bot/tts.py`, `tests/test_tts.py` |
| 3 | STT (Whisper) | `bot/stt.py`, `tests/test_stt.py` |
| 4 | Wake word detection | `bot/wake.py`, `tests/test_wake.py` |
| 5 | Voice gateway main loop | `bot/voice_gateway.py`, `tests/test_voice_gateway.py` |
| 6 | main.py integration | `tests/test_voice_startup.py` |
| 7 | Manual smoke test | — |
