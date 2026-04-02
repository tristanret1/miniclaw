"""Tests for channel base types."""
import pytest
from bot.channel import InboundMessage, ChannelAdapter


class TestInboundMessage:
    def test_create(self):
        msg = InboundMessage(
            channel="test",
            session_key="test:123",
            text="hello",
            image_urls=[],
            reply_ctx={"id": "abc"},
        )
        assert msg.channel == "test"
        assert msg.text == "hello"

    def test_defaults(self):
        msg = InboundMessage(
            channel="test",
            session_key="test:123",
            text="hi",
        )
        assert msg.image_urls == []
        assert msg.reply_ctx == {}


class TestChannelAdapterABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ChannelAdapter()
