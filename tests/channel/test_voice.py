"""Tests for bot.channel.voice — local microphone voice gateway."""

import asyncio
import struct
import pytest
from unittest.mock import AsyncMock, patch


class TestVAD:
    """Voice Activity Detection tests."""

    def test_rms_silent_frame(self):
        """RMS of silence is 0."""
        from bot.channel.voice import compute_rms
        silence = b"\x00" * 3200  # 1600 zero samples (16-bit)
        assert compute_rms(silence) == 0

    def test_rms_loud_frame(self):
        """RMS of a loud frame exceeds threshold."""
        from bot.channel.voice import compute_rms
        loud = struct.pack(f"<{800}h", *([32767] * 800))
        assert compute_rms(loud) > 500

    def test_rms_empty_returns_zero(self):
        from bot.channel.voice import compute_rms
        assert compute_rms(b"") == 0


class TestAudioSegmenter:
    """Audio segmentation by silence tests."""

    def test_segments_on_silence(self):
        """AudioSegmenter yields a segment after silence duration."""
        from bot.channel.voice import AudioSegmenter

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

    @pytest.fixture(autouse=True)
    def reset_conversation_state(self):
        """Ensure each test starts in wake-word-waiting mode."""
        import bot.channel.voice as vg
        vg._active_until = 0.0
        yield
        vg._active_until = 0.0

    @pytest.mark.asyncio
    async def test_wake_word_triggers_llm(self):
        """When wake word detected, utterance is sent to LLM and response is spoken."""
        from bot.channel.voice import _process_utterance

        with patch("bot.channel.voice.stt.transcribe", new_callable=AsyncMock, return_value="miniclaw hello"), \
             patch("bot.channel.voice.wake.check", return_value="hello"), \
             patch("bot.channel.voice.llm.reply", new_callable=AsyncMock, return_value="Hi there!"), \
             patch("bot.channel.voice.tts.synthesize", new_callable=AsyncMock, return_value=b"audio"), \
             patch("bot.channel.voice._play_audio_fallback", new_callable=AsyncMock) as mock_play:

            await _process_utterance(b"fake-audio")

            mock_play.assert_called_once_with(b"audio")

    @pytest.mark.asyncio
    async def test_no_wake_word_not_active_skips_llm(self):
        """When no wake word and not in conversation mode, LLM is not called."""
        from bot.channel.voice import _process_utterance

        with patch("bot.channel.voice.stt.transcribe", new_callable=AsyncMock, return_value="random speech"), \
             patch("bot.channel.voice.wake.check", return_value=None), \
             patch("bot.channel.voice.llm.reply", new_callable=AsyncMock) as mock_llm:

            await _process_utterance(b"fake-audio")

            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_mode_no_wake_word_needed(self):
        """In conversation mode, utterances go to LLM without wake word."""
        import bot.channel.voice as vg
        from bot.channel.voice import _process_utterance

        # Simulate active conversation mode
        vg._activate()

        with patch("bot.channel.voice.stt.transcribe", new_callable=AsyncMock, return_value="what time is it"), \
             patch("bot.channel.voice.wake.check", return_value=None), \
             patch("bot.channel.voice.llm.reply", new_callable=AsyncMock, return_value="It's 3pm") as mock_llm, \
             patch("bot.channel.voice.tts.synthesize", new_callable=AsyncMock, return_value=b"audio"), \
             patch("bot.channel.voice._play_audio_fallback", new_callable=AsyncMock):

            await _process_utterance(b"fake-audio")

            mock_llm.assert_called_once()
            # Check the user content passed to LLM contains the raw text
            call_args = mock_llm.call_args
            assert call_args[0][1] == "what time is it"

    @pytest.mark.asyncio
    async def test_conversation_mode_expires(self):
        """After timeout, conversation mode expires and wake word is needed again."""
        import bot.channel.voice as vg
        from bot.channel.voice import _process_utterance

        # Set active_until to the past (expired)
        vg._active_until = 0.0

        with patch("bot.channel.voice.stt.transcribe", new_callable=AsyncMock, return_value="what time is it"), \
             patch("bot.channel.voice.wake.check", return_value=None), \
             patch("bot.channel.voice.llm.reply", new_callable=AsyncMock) as mock_llm:

            await _process_utterance(b"fake-audio")

            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_wake_word_activates_conversation(self):
        """After wake word, subsequent utterances don't need wake word."""
        import bot.channel.voice as vg
        from bot.channel.voice import _process_utterance, _is_active

        assert not _is_active()

        # First utterance with wake word
        with patch("bot.channel.voice.stt.transcribe", new_callable=AsyncMock, return_value="miniclaw hello"), \
             patch("bot.channel.voice.wake.check", return_value="hello"), \
             patch("bot.channel.voice.llm.reply", new_callable=AsyncMock, return_value="Hi!"), \
             patch("bot.channel.voice.tts.synthesize", new_callable=AsyncMock, return_value=b"audio"), \
             patch("bot.channel.voice._play_audio_fallback", new_callable=AsyncMock):

            await _process_utterance(b"fake-audio")

        # Now should be in active mode
        assert _is_active()

    @pytest.mark.asyncio
    async def test_empty_transcription_skips(self):
        """When STT returns empty, processing stops early."""
        from bot.channel.voice import _process_utterance

        with patch("bot.channel.voice.stt.transcribe", new_callable=AsyncMock, return_value=""), \
             patch("bot.channel.voice.wake.check") as mock_wake:

            await _process_utterance(b"fake-audio")

            mock_wake.assert_not_called()


class TestAnnounce:
    """Voice announce (push notification) tests."""

    @pytest.fixture(autouse=True)
    def setup_queue(self):
        """Ensure announce queue exists for each test."""
        import bot.channel.voice as vg
        vg._announce_queue = asyncio.Queue()
        yield
        vg._announce_queue = None

    @pytest.mark.asyncio
    async def test_announce_queues_message(self):
        """announce() puts a message on the queue."""
        import bot.channel.voice as vg
        from bot.channel.voice import announce

        result = await announce("你好", source="小圆")
        assert "queued" in result
        assert not vg._announce_queue.empty()
        msg, src = vg._announce_queue.get_nowait()
        assert msg == "你好"
        assert src == "小圆"

    @pytest.mark.asyncio
    async def test_announce_without_gateway_returns_error(self):
        """announce() returns error when voice gateway is not running."""
        import bot.channel.voice as vg
        from bot.channel.voice import announce

        vg._announce_queue = None
        result = await announce("test")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_announce_empty_message_returns_error(self):
        """announce() rejects empty messages."""
        from bot.channel.voice import announce

        result = await announce("   ")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_play_announcement_with_source_prefix(self):
        """_play_announcement prefixes the source name."""
        from bot.channel.voice import _play_announcement

        with patch("bot.channel.voice.tts.synthesize", new_callable=AsyncMock, return_value=b"audio") as mock_tts, \
             patch("bot.channel.voice._play_audio_fallback", new_callable=AsyncMock):

            await _play_announcement("提醒你开会", "小圆")

            mock_tts.assert_called_once()
            spoken = mock_tts.call_args[0][0]
            assert "来自小圆的消息" in spoken
            assert "提醒你开会" in spoken

    @pytest.mark.asyncio
    async def test_play_announcement_no_source(self):
        """_play_announcement without source speaks the message directly."""
        from bot.channel.voice import _play_announcement

        with patch("bot.channel.voice.tts.synthesize", new_callable=AsyncMock, return_value=b"audio") as mock_tts, \
             patch("bot.channel.voice._play_audio_fallback", new_callable=AsyncMock):

            await _play_announcement("hello", "")

            spoken = mock_tts.call_args[0][0]
            assert spoken == "hello"

    @pytest.mark.asyncio
    async def test_drain_announcements_plays_all(self):
        """_drain_announcements plays all queued messages in order."""
        import bot.channel.voice as vg
        from bot.channel.voice import _drain_announcements

        vg._announce_queue.put_nowait(("msg1", "agent1"))
        vg._announce_queue.put_nowait(("msg2", "agent2"))

        played = []
        async def fake_play(msg, src):
            played.append((msg, src))

        with patch("bot.channel.voice._play_announcement", new=fake_play), \
             patch("bot.channel.voice._mute"), \
             patch("bot.channel.voice._mute_cooldown"):

            await _drain_announcements()

        assert len(played) == 2
        assert played[0] == ("msg1", "agent1")
        assert played[1] == ("msg2", "agent2")
