"""Voice gateway — local microphone → STT → wake word → LLM → TTS → speaker.

Runs as a peer gateway alongside Discord, SMS, and iMessage.
Audio capture uses PyAudio in a callback thread; processing is async.
"""

from __future__ import annotations

import asyncio
import math
import struct
import tempfile
import time
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

# Set while TTS is playing — suppresses mic input so the bot doesn't hear itself
_playing = False

# Conversation mode: after wake word, stay active for this many seconds of silence
_CONVERSATION_TIMEOUT = 30.0  # seconds without speech before returning to wake mode
_active_until: float = 0.0  # monotonic timestamp; 0 = waiting for wake word


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
    """Play MP3 audio through the default speaker using afplay (macOS) or ffplay.

    Sets _playing flag to suppress mic input during playback so the bot
    doesn't hear and re-process its own TTS output.
    """
    global _playing

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_bytes)
        tmp_path = f.name

    try:
        import shutil
        if shutil.which("afplay"):
            cmd = ["afplay", tmp_path]
        else:
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", tmp_path]

        _playing = True
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    finally:
        _playing = False
        Path(tmp_path).unlink(missing_ok=True)


# ── Utterance processing ─────────────────────────────────────────────────────


def _is_active() -> bool:
    """Check if we're in active conversation mode (wake word already said)."""
    return time.monotonic() < _active_until


def _activate() -> None:
    """Enter/extend active conversation mode."""
    global _active_until
    _active_until = time.monotonic() + _CONVERSATION_TIMEOUT
    log.debug("conversation active for %.0fs", _CONVERSATION_TIMEOUT)


def _deactivate() -> None:
    """Return to wake word listening mode."""
    global _active_until
    _active_until = 0.0


async def _process_utterance(audio_bytes: bytes) -> None:
    """Process a single utterance: STT → (wake check or active mode) → LLM → TTS → play.

    After wake word is detected, enters conversation mode for _CONVERSATION_TIMEOUT
    seconds. During conversation mode, all utterances go directly to the LLM
    without needing a wake word.
    """
    # 1. Transcribe
    text = await stt.transcribe(audio_bytes)
    if not text:
        return

    log.info("heard: %s", text[:200])

    # 2. Determine user text — wake word or active conversation
    if _is_active():
        # Already in conversation mode — send directly, also check for wake word
        # in case user says it again (strip it if present)
        command = wake.check(text)
        user_text = command if command is not None else text
    else:
        # Waiting for wake word
        command = wake.check(text)
        if command is None:
            log.debug("no wake word, not active — ignoring")
            return
        user_text = command
        log.info("wake word detected!")

    # Enter/extend conversation mode
    _activate()

    # If wake word only (no command), use a greeting prompt
    if not user_text:
        user_text = "hey"

    log.info("command: %s", user_text[:200])
    user_content = build_user_content(user_text, [])

    # 3. LLM
    reply_text = await llm.reply(SESSION_KEY, user_content)
    if not reply_text.strip():
        return

    log.info("reply: %s", reply_text[:200])

    # Extend conversation mode after getting a reply
    _activate()

    # 4. TTS
    audio = await tts.synthesize(reply_text, provider=TTS_PROVIDER)

    # 5. Play
    await _play_audio(audio)

    # Extend again after playback so user has time to respond
    _activate()


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
            # Skip mic input while TTS is playing to avoid hearing ourselves
            if _playing:
                segmenter.reset()
                continue
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
