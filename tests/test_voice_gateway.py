"""Tests for bot.voice_gateway — local microphone voice gateway."""

import struct
import pytest
from unittest.mock import AsyncMock, patch


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
        loud = struct.pack(f"<{800}h", *([32767] * 800))
        assert compute_rms(loud) > 500

    def test_rms_empty_returns_zero(self):
        from bot.voice_gateway import compute_rms
        assert compute_rms(b"") == 0


class TestAudioSegmenter:
    """Audio segmentation by silence tests."""

    def test_segments_on_silence(self):
        """AudioSegmenter yields a segment after silence duration."""
        from bot.voice_gateway import AudioSegmenter

        segmenter = AudioSegmenter(
            silence_threshold=100,
            silence_duration=0.2,  # 200ms — needs 2 silent frames at 100ms each
            sample_rate=16000,
            frame_size=1600,  # 100ms frames (1600 samples * 2 bytes = 3200 bytes)
        )

        # Feed one loud frame then silent frames
        loud_frame = struct.pack(f"<{800}h", *([10000] * 800))
        silent_frame = b"\x00" * 1600

        result = segmenter.feed(loud_frame)
        assert result is None  # still speaking

        result = segmenter.feed(silent_frame)
        assert result is None  # silence just started, need more

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

        with patch("bot.voice_gateway.stt.transcribe", new_callable=AsyncMock, return_value="miniclaw hello"), \
             patch("bot.voice_gateway.wake.check", return_value="hello"), \
             patch("bot.voice_gateway.llm.reply", new_callable=AsyncMock, return_value="Hi there!"), \
             patch("bot.voice_gateway.tts.synthesize", new_callable=AsyncMock, return_value=b"audio"), \
             patch("bot.voice_gateway._play_audio", new_callable=AsyncMock) as mock_play:

            await _process_utterance(b"fake-audio")

            mock_play.assert_called_once_with(b"audio")

    @pytest.mark.asyncio
    async def test_no_wake_word_skips_llm(self):
        """When no wake word detected, LLM is not called."""
        from bot.voice_gateway import _process_utterance

        with patch("bot.voice_gateway.stt.transcribe", new_callable=AsyncMock, return_value="random speech"), \
             patch("bot.voice_gateway.wake.check", return_value=None), \
             patch("bot.voice_gateway.llm.reply", new_callable=AsyncMock) as mock_llm:

            await _process_utterance(b"fake-audio")

            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_transcription_skips(self):
        """When STT returns empty, processing stops early."""
        from bot.voice_gateway import _process_utterance

        with patch("bot.voice_gateway.stt.transcribe", new_callable=AsyncMock, return_value=""), \
             patch("bot.voice_gateway.wake.check") as mock_wake:

            await _process_utterance(b"fake-audio")

            mock_wake.assert_not_called()
