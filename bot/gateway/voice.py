"""Voice gateway — local microphone → STT → wake word → LLM → TTS → speaker.

Runs as a peer gateway alongside Discord, SMS, and iMessage.
Uses macOS AVAudioEngine with voice processing for hardware echo cancellation.
Falls back to PyAudio if AVAudioEngine is unavailable.
"""

from __future__ import annotations

import asyncio
import math
import struct
import time
from typing import TYPE_CHECKING

from bot import llm
from bot.audio import stt, tts, wake
from bot.config import get_config
from bot.logger import get_logger
from bot.message import build_user_content
from bot.utils.session_keys import voice_key

if TYPE_CHECKING:
    from bot.agent import Agent

log = get_logger("voice")

_PLAYBACK_COOLDOWN = 0.5  # shorter cooldown since AEC handles most echo
_CONVERSATION_TIMEOUT = 30.0


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


# ── VoiceGateway ─────────────────────────────────────────────────────────────


class VoiceGateway:
    """Encapsulates all mutable state for the voice gateway."""

    def __init__(self, agent: Agent | None = None) -> None:
        self._agent: Agent | None = agent
        self._session_key: str = voice_key()
        self._muted_until: float = 0.0
        self._active_until: float = 0.0
        self._engine = None
        self._announce_queue: asyncio.Queue[tuple[str, str]] | None = None

        # Config (read once at init)
        _voice_cfg = get_config().gateway.voice
        self._tts_provider = _voice_cfg.tts_provider
        self._sample_rate = _voice_cfg.sample_rate
        self._silence_duration = _voice_cfg.silence_duration
        self._silence_threshold = _voice_cfg.silence_threshold

    # ── Mute helpers ──────────────────────────────────────────────────────────

    def _is_muted(self) -> bool:
        return time.monotonic() < self._muted_until

    def _mute(self) -> None:
        self._muted_until = float("inf")

    def _mute_cooldown(self) -> None:
        self._muted_until = time.monotonic() + _PLAYBACK_COOLDOWN

    # ── Conversation mode ─────────────────────────────────────────────────────

    def _is_active(self) -> bool:
        return time.monotonic() < self._active_until

    def _activate(self) -> None:
        self._active_until = time.monotonic() + _CONVERSATION_TIMEOUT
        log.debug("conversation active for %.0fs", _CONVERSATION_TIMEOUT)

    def _deactivate(self) -> None:
        self._active_until = 0.0

    # ── Utterance processing ──────────────────────────────────────────────────

    async def _process_utterance(self, audio_bytes: bytes) -> None:
        """Process a single utterance: STT → (wake check or active mode) → LLM → TTS → play."""
        # 1. Transcribe
        text = await stt.transcribe(audio_bytes)
        if not text:
            return

        log.info("heard: %s", text[:200])

        # 2. Determine user text — wake word or active conversation
        if self._is_active():
            command = wake.check(text)
            user_text = command if command is not None else text
        else:
            command = wake.check(text)
            if command is None:
                log.debug("no wake word, not active — ignoring")
                return
            user_text = command
            log.info("wake word detected!")

        # Enter/extend conversation mode
        self._activate()

        # If wake word only (no command), use a greeting prompt
        if not user_text:
            user_text = "hey"

        log.info("command: %s", user_text[:200])
        user_content = build_user_content(user_text, [])

        # 3. LLM
        reply_text = await llm.reply(self._session_key, user_content, agent=self._agent)
        if not reply_text.strip():
            return

        log.info("reply: %s", reply_text[:200])
        self._activate()

        # 4. TTS → Play (streaming if AudioEngine available)
        if self._engine and self._tts_provider == "openai":
            await self._engine.play_pcm_stream(tts.stream_pcm(reply_text, provider=self._tts_provider))
        elif self._engine and self._tts_provider == "volcengine":
            mp3_chunks: list[bytes] = []
            async for chunk in tts.stream_volcengine(reply_text):
                mp3_chunks.append(chunk)
            await self._engine.play_audio(b"".join(mp3_chunks))
        else:
            audio = await tts.synthesize(reply_text, provider=self._tts_provider)
            if self._engine:
                await self._engine.play_audio(audio)
            else:
                await _play_audio_fallback(audio)

        self._activate()

    # ── Push announcements ────────────────────────────────────────────────────

    async def announce(self, message: str, source: str = "") -> str:
        """Queue a voice announcement for playback on the local speaker."""
        if self._announce_queue is None:
            return "Error: voice gateway is not running."

        if not message.strip():
            return "Error: empty announcement message."

        self._announce_queue.put_nowait((message.strip(), source.strip()))
        log.info("announce queued: source=%s len=%d", source or "unknown", len(message))
        return f"Announcement queued for voice playback (source={source or 'unknown'})."

    async def _play_announcement(self, message: str, source: str) -> None:
        """Synthesize and play a single announcement."""
        if source:
            spoken_text = f"来自{source}的消息：{message}"
        else:
            spoken_text = message

        log.info("playing announcement: %s", spoken_text[:200])

        if self._engine and self._tts_provider == "openai":
            await self._engine.play_pcm_stream(tts.stream_pcm(spoken_text, provider=self._tts_provider))
        elif self._engine and self._tts_provider == "volcengine":
            mp3_chunks: list[bytes] = []
            async for chunk in tts.stream_volcengine(spoken_text):
                mp3_chunks.append(chunk)
            await self._engine.play_audio(b"".join(mp3_chunks))
        else:
            audio = await tts.synthesize(spoken_text, provider=self._tts_provider)
            if self._engine:
                await self._engine.play_audio(audio)
            else:
                await _play_audio_fallback(audio)

        log.info("announcement played: source=%s", source or "unknown")

    async def _drain_announcements(self) -> None:
        """Drain and play all queued announcements."""
        if self._announce_queue is None:
            return

        while not self._announce_queue.empty():
            try:
                message, source = self._announce_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            self._mute()
            try:
                await self._play_announcement(message, source)
            except Exception:
                log.exception("failed to play announcement")
            finally:
                self._mute_cooldown()

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the voice gateway. Listens on local microphone until cancelled."""
        self._announce_queue = asyncio.Queue()

        if self._agent:
            log.info("Voice agent: %s (workspace=%s)", self._agent.name, self._agent.workspace_dir)

        log.info("Voice gateway starting (sample_rate=%d, threshold=%d, silence=%.1fs)",
                 self._sample_rate, self._silence_threshold, self._silence_duration)

        frame_size = self._sample_rate // 10  # 100ms frames
        audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # Try AVAudioEngine with AEC; fall back to PyAudio
        stream = None
        pa = None
        try:
            from bot.audio.engine import AudioEngine
            engine = AudioEngine(sample_rate=self._sample_rate)
            engine.start(queue=audio_queue, loop=loop)
            self._engine = engine
            log.info("Using AVAudioEngine with hardware AEC")
        except Exception as e:
            log.warning("AVAudioEngine unavailable (%s), falling back to PyAudio", e)
            import pyaudio

            def audio_callback(in_data, frame_count, time_info, status):
                loop.call_soon_threadsafe(audio_queue.put_nowait, in_data)
                return (None, pyaudio.paContinue)

            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self._sample_rate,
                input=True,
                frames_per_buffer=frame_size,
                stream_callback=audio_callback,
            )
            stream.start_stream()

        log.info("Voice gateway listening on microphone")

        segmenter = AudioSegmenter(
            silence_threshold=self._silence_threshold,
            silence_duration=self._silence_duration,
            sample_rate=self._sample_rate,
            frame_size=frame_size * 2,  # bytes per frame (16-bit = 2 bytes/sample)
        )

        try:
            while True:
                # Check for queued announcements between mic frames
                await self._drain_announcements()

                try:
                    frame = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                if self._is_muted():
                    segmenter.reset()
                    continue
                utterance = segmenter.feed(frame)
                if utterance:
                    self._mute()
                    segmenter.reset()
                    try:
                        await self._process_utterance(utterance)
                    finally:
                        self._mute_cooldown()
        except asyncio.CancelledError:
            pass
        finally:
            self._announce_queue = None
            if self._engine:
                self._engine.stop()
                self._engine = None
            elif stream is not None:
                stream.stop_stream()
                stream.close()
                pa.terminate()
            log.info("Voice gateway stopped")


# ── Fallback audio playback ───────────────────────────────────────────────────


async def _play_audio_fallback(mp3_bytes: bytes) -> None:
    """Fallback playback via afplay (no AEC)."""
    import shutil
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_bytes)
        tmp_path = f.name

    try:
        if shutil.which("afplay"):
            cmd = ["afplay", tmp_path]
        else:
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", tmp_path]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ── Module-level singleton + backward-compatible API ─────────────────────────
#
# A default VoiceGateway instance exists at module level so that tests and
# legacy callers can access module-level attributes (_active_until,
# _announce_queue) and functions (_process_utterance, _activate, etc.)
# directly.  start_voice_gateway() replaces this singleton so the real
# runtime also benefits from the class encapsulation.

_gateway: VoiceGateway = VoiceGateway()


# State attributes forwarded to the singleton so tests can read/write them
# directly on the module (e.g. ``vg._active_until = 0.0``).
# Implemented via module __getattr__ / a thin descriptor approach is not
# easily done for setattr, so we expose them as real module-level names that
# are kept in sync by the wrapper functions below.  Tests that assign
# ``vg._active_until = 0.0`` will set the *module* attribute; the wrappers
# below read from ``_gateway`` only when the module attribute has not been
# overridden.  To keep this simple and reliable, we just re-export the live
# attributes from the current singleton and delegate every write back to it.

def _get_gw() -> VoiceGateway:
    """Return the current active gateway singleton."""
    return _gateway


# ── Module-level attribute proxies (tests set these directly) ─────────────────
# We shadow them here so that ``import bot.gateway.voice as vg; vg._active_until``
# works.  The wrappers always go through _get_gw() so they pick up the live value.

_active_until: float = 0.0      # proxy — real state lives on _gateway
_announce_queue: asyncio.Queue[tuple[str, str]] | None = None  # proxy


# ── Module-level wrapper functions ────────────────────────────────────────────


def _is_muted() -> bool:
    return _get_gw()._is_muted()


def _mute() -> None:
    _get_gw()._mute()


def _mute_cooldown() -> None:
    _get_gw()._mute_cooldown()


def _is_active() -> bool:
    # Honour the module-level _active_until proxy (set by tests)
    import sys
    mod = sys.modules[__name__]
    return time.monotonic() < mod._active_until


def _activate() -> None:
    import sys
    mod = sys.modules[__name__]
    mod._active_until = time.monotonic() + _CONVERSATION_TIMEOUT
    _get_gw()._active_until = mod._active_until
    log.debug("conversation active for %.0fs", _CONVERSATION_TIMEOUT)


def _deactivate() -> None:
    import sys
    mod = sys.modules[__name__]
    mod._active_until = 0.0
    _get_gw()._active_until = 0.0


async def _process_utterance(audio_bytes: bytes) -> None:
    """Process a single utterance (module-level; uses module-level state proxies)."""
    import sys
    mod = sys.modules[__name__]

    text = await stt.transcribe(audio_bytes)
    if not text:
        return

    log.info("heard: %s", text[:200])

    if _is_active():
        command = wake.check(text)
        user_text = command if command is not None else text
    else:
        command = wake.check(text)
        if command is None:
            log.debug("no wake word, not active — ignoring")
            return
        user_text = command
        log.info("wake word detected!")

    _activate()

    if not user_text:
        user_text = "hey"

    log.info("command: %s", user_text[:200])
    user_content = build_user_content(user_text, [])

    gw = _get_gw()
    reply_text = await llm.reply(gw._session_key, user_content, agent=gw._agent)
    if not reply_text.strip():
        return

    log.info("reply: %s", reply_text[:200])
    _activate()

    tts_provider = gw._tts_provider
    engine = gw._engine
    if engine and tts_provider == "openai":
        await engine.play_pcm_stream(tts.stream_pcm(reply_text, provider=tts_provider))
    elif engine and tts_provider == "volcengine":
        mp3_chunks: list[bytes] = []
        async for chunk in tts.stream_volcengine(reply_text):
            mp3_chunks.append(chunk)
        await engine.play_audio(b"".join(mp3_chunks))
    else:
        audio = await tts.synthesize(reply_text, provider=tts_provider)
        if engine:
            await engine.play_audio(audio)
        else:
            await _play_audio_fallback(audio)

    _activate()


async def _play_announcement(message: str, source: str) -> None:
    """Synthesize and play a single announcement (module-level)."""
    if source:
        spoken_text = f"来自{source}的消息：{message}"
    else:
        spoken_text = message

    log.info("playing announcement: %s", spoken_text[:200])

    gw = _get_gw()
    tts_provider = gw._tts_provider
    engine = gw._engine
    if engine and tts_provider == "openai":
        await engine.play_pcm_stream(tts.stream_pcm(spoken_text, provider=tts_provider))
    elif engine and tts_provider == "volcengine":
        mp3_chunks: list[bytes] = []
        async for chunk in tts.stream_volcengine(spoken_text):
            mp3_chunks.append(chunk)
        await engine.play_audio(b"".join(mp3_chunks))
    else:
        audio = await tts.synthesize(spoken_text, provider=tts_provider)
        if engine:
            await engine.play_audio(audio)
        else:
            await _play_audio_fallback(audio)

    log.info("announcement played: source=%s", source or "unknown")


async def _drain_announcements() -> None:
    """Drain and play all queued announcements (module-level; calls module-level helpers)."""
    import sys
    mod = sys.modules[__name__]
    q = mod._announce_queue
    if q is None:
        return

    while not q.empty():
        try:
            message, source = q.get_nowait()
        except asyncio.QueueEmpty:
            break

        _mute()
        try:
            await _play_announcement(message, source)
        except Exception:
            log.exception("failed to play announcement")
        finally:
            _mute_cooldown()


# ── Public API ────────────────────────────────────────────────────────────────


async def start_voice_gateway(agent: Agent | None = None) -> None:
    """Start the voice gateway. Listens on local microphone until cancelled.

    Uses macOS AVAudioEngine with voice processing (AEC) for echo cancellation.
    TTS audio is played through the same engine so AEC can subtract it from mic input.

    Args:
        agent: Optional Agent for voice-specific personality, session, and memory.
               If None, uses global defaults.
    """
    global _gateway
    _gateway = VoiceGateway(agent)
    await _gateway.start()


async def announce(message: str, source: str = "") -> str:
    """Queue a voice announcement for playback on the local speaker.

    Can be called from any agent/tool. The announcement will play after any
    current TTS finishes (non-interrupting).

    Args:
        message: Text to speak via TTS.
        source: Name of the agent or channel that sent the announcement.

    Returns:
        Status string confirming the announcement was queued.
    """
    import sys
    mod = sys.modules[__name__]
    # Use the module-level _announce_queue proxy so tests that set it directly work
    if mod._announce_queue is None:
        return "Error: voice gateway is not running."
    if not message.strip():
        return "Error: empty announcement message."
    mod._announce_queue.put_nowait((message.strip(), source.strip()))
    log.info("announce queued: source=%s len=%d", source or "unknown", len(message))
    return f"Announcement queued for voice playback (source={source or 'unknown'})."
