"""Tests for bot.stt — STT (speech-to-text) provider."""

import pytest
from unittest.mock import AsyncMock, MagicMock


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

        result = await transcribe(b"\x00" * 32000, client=mock_client)
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_transcribe_passes_model(self):
        """transcribe() passes the configured model to Whisper API."""
        from bot.stt import transcribe

        mock_transcription = MagicMock()
        mock_transcription.text = "test"

        mock_client = AsyncMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcription)

        await transcribe(b"\x00" * 32000, client=mock_client, model="whisper-1")
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

        await transcribe(b"\x00" * 32000, client=mock_client, sample_rate=16000)
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
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

        result = await transcribe(b"\x00" * 32000, client=mock_client)
        assert result == ""

    @pytest.mark.asyncio
    async def test_transcribe_short_audio_skipped(self):
        """transcribe() returns empty for audio shorter than 0.5s."""
        from bot.stt import transcribe

        result = await transcribe(b"\x00" * 100)  # way too short
        assert result == ""
