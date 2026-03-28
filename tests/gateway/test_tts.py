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
        """synthesize_openai() passes model and voice from args."""
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
            {"type": "WordBoundary", "data": None},
            {"type": "audio", "data": b"chunk2"},
        ]

        with patch("bot.tts.edge_tts") as mock_edge:
            mock_communicate = AsyncMock()

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
