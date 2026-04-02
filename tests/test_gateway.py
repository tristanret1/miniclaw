"""Tests for Gateway exchange."""
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
        adapter = FakeAdapter()
        gw = Gateway()
        gw.register_adapter(adapter)
        gw.register_agent("default", MagicMock())
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
        adapter = FakeAdapter()
        gw = Gateway()
        gw.register_adapter(adapter)
        gw.register_agent("default", MagicMock())
        await adapter.start(gw)

        msg = InboundMessage(channel="fake", session_key="k", text="hi")
        await gw.handle(msg)
        assert len(adapter.sent) == 0

    @patch("bot.gateway.llm")
    async def test_handle_no_adapter(self, mock_llm):
        gw = Gateway()
        msg = InboundMessage(channel="missing", session_key="k", text="hi")
        await gw.handle(msg)  # should not raise

    def test_register_adapter(self):
        gw = Gateway()
        adapter = FakeAdapter()
        gw.register_adapter(adapter)
        assert gw.get_adapter("fake") is adapter

    def test_get_adapter_missing(self):
        gw = Gateway()
        assert gw.get_adapter("nope") is None

    def test_channel_agent_mapping(self):
        gw = Gateway()
        agent = MagicMock()
        gw.register_agent("feishu_agent", agent)
        gw.set_channel_agent("feishu", "feishu_agent")
        assert gw.get_agent("feishu") is agent

    def test_default_agent_fallback(self):
        gw = Gateway()
        agent = MagicMock()
        gw.register_agent("default", agent)
        assert gw.get_agent("unknown_channel") is agent

    @patch("bot.gateway.llm")
    async def test_deliver(self, mock_llm):
        adapter = FakeAdapter()
        gw = Gateway()
        gw.register_adapter(adapter)

        result = await gw.deliver("fake", {"target": "123"}, "hello")
        assert result == "ok"
        assert adapter.sent == [({"target": "123"}, "hello")]

    async def test_deliver_missing_adapter(self):
        gw = Gateway()
        result = await gw.deliver("missing", {}, "hello")
        assert "Error" in result
