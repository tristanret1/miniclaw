"""macOS AVAudioEngine wrapper with voice processing (AEC).

Uses Apple's built-in echo cancellation so the mic doesn't pick up
audio played through the speakers. The engine:
1. Captures mic input with AEC enabled (subtracts speaker output)
2. Plays TTS audio through AVAudioPlayerNode (provides AEC reference signal)
"""

from __future__ import annotations

import asyncio
import array
import tempfile
import time
from pathlib import Path

from AVFoundation import AVAudioEngine, AVAudioFile, AVAudioPlayerNode
from Foundation import NSURL

from bot.config import VOICE_SAMPLE_RATE
from bot.logger import get_logger

log = get_logger("audio_engine")


class AudioEngine:
    """AVAudioEngine wrapper with voice processing AEC.

    Replaces PyAudio for both capture and playback. Voice processing
    automatically cancels speaker output from mic input.
    """

    def __init__(self, sample_rate: int | None = None):
        self._target_rate = sample_rate or VOICE_SAMPLE_RATE
        self._engine: AVAudioEngine | None = None
        self._player: AVAudioPlayerNode | None = None
        self._queue: asyncio.Queue[bytes] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._native_rate: float = 48000.0
        self._downsample_ratio: int = 1

    def start(self, queue: asyncio.Queue[bytes], loop: asyncio.AbstractEventLoop) -> None:
        """Start the audio engine with voice processing AEC."""
        self._queue = queue
        self._loop = loop

        self._engine = AVAudioEngine.alloc().init()
        input_node = self._engine.inputNode()

        # Enable voice processing (AEC) while engine is stopped
        success, err = input_node.setVoiceProcessingEnabled_error_(True, None)
        if success:
            log.info("Voice processing (AEC) enabled")
        else:
            log.warning("Failed to enable voice processing: %s", err)

        # Start engine
        ok, err = self._engine.startAndReturnError_(None)
        if not ok:
            raise RuntimeError(f"AVAudioEngine failed to start: {err}")

        # Attach player node AFTER engine starts (avoids format conflict)
        self._player = AVAudioPlayerNode.alloc().init()
        self._engine.attachNode_(self._player)
        mixer = self._engine.mainMixerNode()
        self._engine.connect_to_format_(self._player, mixer, None)
        self._player.play()

        # Get native format and compute downsample ratio
        native_fmt = input_node.outputFormatForBus_(0)
        self._native_rate = native_fmt.sampleRate()
        self._downsample_ratio = max(1, int(self._native_rate / self._target_rate))
        log.info("Capture: %.0fHz %dch → downsample %dx → %dHz mono",
                 self._native_rate, native_fmt.channelCount(),
                 self._downsample_ratio, self._target_rate)

        # Install tap on input bus (uses native format — we downsample in callback)
        buffer_size = int(self._native_rate / 10)  # ~100ms
        input_node.installTapOnBus_bufferSize_format_block_(
            0, buffer_size, native_fmt, self._on_audio_buffer
        )

        log.info("AudioEngine started with AEC")

    def _on_audio_buffer(self, buffer, when) -> None:
        """Called from audio thread with captured mic data (AEC-processed)."""
        frame_count = buffer.frameLength()
        if frame_count == 0:
            return

        channel_data = buffer.floatChannelData()
        if channel_data is None:
            return

        # Read float32 samples from channel 0 (mono)
        ptr = channel_data[0]
        ratio = self._downsample_ratio

        # Downsample and convert float32 → int16 PCM
        out_count = frame_count // ratio
        pcm = array.array("h", (0,) * out_count)
        for i in range(out_count):
            sample = ptr[i * ratio]
            clamped = max(-1.0, min(1.0, sample))
            pcm[i] = int(clamped * 32767)

        if self._queue and self._loop:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, pcm.tobytes())

    async def play_audio(self, mp3_bytes: bytes) -> None:
        """Play MP3 audio through the engine (provides AEC reference signal).

        The engine's voice processing will automatically cancel this audio
        from the mic input.
        """
        if not self._player or not self._engine:
            log.warning("AudioEngine not started, cannot play")
            return

        # Write to temp file for AVAudioFile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(mp3_bytes)
            tmp_path = f.name

        try:
            url = NSURL.fileURLWithPath_(tmp_path)
            audio_file, err = AVAudioFile.alloc().initForReading_error_(url, None)
            if not audio_file:
                log.error("Failed to load audio file: %s", err)
                return

            # Schedule and wait for completion
            done_event = asyncio.Event()

            def on_complete():
                if self._loop:
                    self._loop.call_soon_threadsafe(done_event.set)

            self._player.scheduleFile_atTime_completionHandler_(
                audio_file, None, on_complete
            )

            await done_event.wait()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def stop(self) -> None:
        """Stop the audio engine."""
        if not self._engine:
            return

        try:
            input_node = self._engine.inputNode()
            input_node.removeTapOnBus_(0)
        except Exception:
            pass

        if self._player:
            self._player.stop()
        self._engine.stop()
        self._engine = None
        self._player = None
        log.info("AudioEngine stopped")
