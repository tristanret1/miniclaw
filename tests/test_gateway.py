"""Tests for Gateway exchange (single agent)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot.channel import InboundMessage, ChannelAdapter
from bot.gateway import Gateway


class FakeAdapter(ChannelAdapter):
    name = "fake"
    supports_streaming = False

    def __init__(self):
        self.sent = []
        self._gateway = None

    async def start(self, gateway):
        self._gateway = gateway

    async def stop(self):
        pass

    async def send(self, reply_ctx, text):
        self.sent.append((reply_ctx, text))
        return "ok"


class TestGateway:
    @patch("bot.gateway.llm")
    async def test_handle_non_streaming(self, mock_llm):
        mock_llm.reply = AsyncMock(return_value="hello back")
        agent = MagicMock()
        adapter = FakeAdapter()
        gw = Gateway(agent)
        gw.register_adapter(adapter)
        await adapter.start(gw)

        msg = InboundMessage(
            channel="fake",
            session_key="fake:123",
            text="hello",
            reply_ctx={"id": "msg1"},
        )
        await gw.handle(msg)

        assert len(adapter.sent) == 1
        assert adapter.sent[0][1] == "hello back"

    @patch("bot.gateway.llm")
    async def test_handle_empty_reply_not_sent(self, mock_llm):
        mock_llm.reply = AsyncMock(return_value="   ")
        agent = MagicMock()
        adapter = FakeAdapter()
        gw = Gateway(agent)
        gw.register_adapter(adapter)
        await adapter.start(gw)

        msg = InboundMessage(channel="fake", session_key="k", text="hi")
        await gw.handle(msg)
        assert len(adapter.sent) == 0

    @patch("bot.gateway.llm")
    async def test_handle_no_adapter(self, mock_llm):
        gw = Gateway(MagicMock())
        msg = InboundMessage(channel="missing", session_key="k", text="hi")
        await gw.handle(msg)  # should not raise

    def test_register_adapter(self):
        gw = Gateway(MagicMock())
        adapter = FakeAdapter()
        gw.register_adapter(adapter)
        assert gw.get_adapter("fake") is adapter

    def test_get_adapter_missing(self):
        gw = Gateway(MagicMock())
        assert gw.get_adapter("nope") is None

    @patch("bot.gateway.llm")
    async def test_deliver(self, mock_llm):
        adapter = FakeAdapter()
        gw = Gateway(MagicMock())
        gw.register_adapter(adapter)

        result = await gw.deliver("fake", {"target": "123"}, "hello")
        assert result == "ok"
        assert adapter.sent == [({"target": "123"}, "hello")]

    async def test_deliver_missing_adapter(self):
        gw = Gateway(MagicMock())
        result = await gw.deliver("missing", {}, "hello")
        assert "Error" in result
