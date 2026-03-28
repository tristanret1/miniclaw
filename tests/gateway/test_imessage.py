"""Tests for iMessage gateway — JSON-RPC client and message handling."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── RPC Client tests ────────────────────────────────────────────────────────

class TestIMessageRpcClient:
    """Test the JSON-RPC client line parsing and dispatching."""

    def test_handle_line_response(self):
        """Successful response resolves the pending future."""
        from bot.gateway.imessage import IMessageRpcClient

        client = IMessageRpcClient()
        loop = asyncio.new_event_loop()
        fut = loop.create_future()
        client._pending["1"] = fut

        client._handle_line('{"jsonrpc":"2.0","id":1,"result":{"ok":"sent"}}')

        assert fut.done()
        assert fut.result() == {"ok": "sent"}
        loop.close()

    def test_handle_line_error_response(self):
        """Error response rejects the pending future."""
        from bot.gateway.imessage import IMessageRpcClient

        client = IMessageRpcClient()
        loop = asyncio.new_event_loop()
        fut = loop.create_future()
        client._pending["2"] = fut

        client._handle_line('{"jsonrpc":"2.0","id":2,"error":{"message":"not found"}}')

        assert fut.done()
        with pytest.raises(RuntimeError, match="not found"):
            fut.result()
        loop.close()

    def test_handle_line_notification(self):
        """Notifications dispatch to the callback."""
        from bot.gateway.imessage import IMessageRpcClient

        client = IMessageRpcClient()
        notifications = []
        client._on_notification = lambda method, params: notifications.append((method, params))

        client._handle_line('{"method":"message","params":{"sender":"+1234","text":"hello"}}')

        assert len(notifications) == 1
        assert notifications[0] == ("message", {"sender": "+1234", "text": "hello"})

    def test_handle_line_invalid_json(self):
        """Invalid JSON is silently ignored."""
        from bot.gateway.imessage import IMessageRpcClient

        client = IMessageRpcClient()
        # Should not raise
        client._handle_line("not json at all")

    def test_handle_line_empty(self):
        """Empty line is ignored."""
        from bot.gateway.imessage import IMessageRpcClient

        client = IMessageRpcClient()
        client._handle_line("")


# ── Handle normalization ────────────────────────────────────────────────────

class TestNormalizeHandle:
    def test_phone_number(self):
        from bot.gateway.imessage import _normalize_handle
        assert _normalize_handle("+14155551234") == "+14155551234"

    def test_email(self):
        from bot.gateway.imessage import _normalize_handle
        assert _normalize_handle("User@iCloud.com") == "user@icloud.com"

    def test_strip_service_prefix(self):
        from bot.gateway.imessage import _normalize_handle
        assert _normalize_handle("imessage:user@icloud.com") == "user@icloud.com"

    def test_strip_whitespace(self):
        from bot.gateway.imessage import _normalize_handle
        assert _normalize_handle("  +1234  ") == "+1234"


# ── Allowlist ───────────────────────────────────────────────────────────────

class TestIsAllowed:
    def test_empty_allowlist_allows_all(self, test_config):
        test_config.gateway.imessage.allow_from = []
        from bot.gateway.imessage import _is_allowed
        assert _is_allowed("+14155551234") is True

    def test_allowed_phone(self, test_config):
        test_config.gateway.imessage.allow_from = ["+14155551234", "friend@icloud.com"]
        from bot.gateway.imessage import _is_allowed
        assert _is_allowed("+14155551234") is True

    def test_blocked_phone(self, test_config):
        test_config.gateway.imessage.allow_from = ["+14155551234"]
        from bot.gateway.imessage import _is_allowed
        assert _is_allowed("+19876543210") is False

    def test_case_insensitive(self, test_config):
        test_config.gateway.imessage.allow_from = ["user@icloud.com"]
        from bot.gateway.imessage import _is_allowed
        assert _is_allowed("User@iCloud.com") is True


# ── Message processing ─────────────────────────────────────────────────────

class TestProcessMessage:
    @pytest.mark.asyncio
    async def test_process_message_sends_reply(self):
        """Incoming message triggers LLM reply and sends iMessage back."""
        from bot.gateway.imessage import _process_message, IMessageRpcClient

        client = MagicMock(spec=IMessageRpcClient)
        client.request = AsyncMock(return_value={"ok": "sent"})

        with patch("bot.llm.reply", new_callable=AsyncMock, return_value="Hello back!"):
            await _process_message(client, "+14155551234", "Hi there")

        client.request.assert_called_once()
        call_args = client.request.call_args
        assert call_args[0][0] == "send"
        assert call_args[0][1]["text"] == "Hello back!"

    @pytest.mark.asyncio
    async def test_process_message_empty_reply_no_send(self):
        """Empty LLM reply doesn't trigger a send."""
        from bot.gateway.imessage import _process_message, IMessageRpcClient

        client = MagicMock(spec=IMessageRpcClient)
        client.request = AsyncMock()

        with patch("bot.llm.reply", new_callable=AsyncMock, return_value="   "):
            await _process_message(client, "+14155551234", "Hi")

        client.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_uses_session_key(self):
        """Session key is imessage:{normalized_handle}."""
        from bot.gateway.imessage import _process_message, IMessageRpcClient

        client = MagicMock(spec=IMessageRpcClient)
        client.request = AsyncMock(return_value={"ok": "sent"})

        with patch("bot.llm.reply", new_callable=AsyncMock, return_value="reply") as mock_reply:
            await _process_message(client, "User@iCloud.com", "test")

        mock_reply.assert_called_once()
        assert mock_reply.call_args[0][0] == "imessage:user@icloud.com"


# ── Send function ───────────────────────────────────────────────────────────

class TestSendIMessage:
    @pytest.mark.asyncio
    async def test_send_with_phone(self):
        from bot.gateway.imessage import send_imessage, IMessageRpcClient

        client = MagicMock(spec=IMessageRpcClient)
        client.request = AsyncMock(return_value={"messageId": "abc123"})

        result = await send_imessage(client, to="+14155551234", message="Hello!")

        client.request.assert_called_once_with("send", {
            "text": "Hello!",
            "service": "auto",
            "to": "+14155551234",
        })
        assert "abc123" in result

    @pytest.mark.asyncio
    async def test_send_with_chat_id(self):
        from bot.gateway.imessage import send_imessage, IMessageRpcClient

        client = MagicMock(spec=IMessageRpcClient)
        client.request = AsyncMock(return_value={"ok": "sent"})

        await send_imessage(client, to="+1234", message="Hi", chat_id=42)

        call_args = client.request.call_args[0][1]
        assert call_args["chat_id"] == 42
        assert "to" not in call_args

    @pytest.mark.asyncio
    async def test_send_error(self):
        from bot.gateway.imessage import send_imessage, IMessageRpcClient

        client = MagicMock(spec=IMessageRpcClient)
        client.request = AsyncMock(side_effect=RuntimeError("connection lost"))

        result = await send_imessage(client, to="+1234", message="Hi")
        assert "Error" in result


# ── Tool dispatch ───────────────────────────────────────────────────────────

class TestToolDispatch:
    @pytest.mark.asyncio
    async def test_imessage_send_tool_uses_gateway_client(self):
        """When gateway is running, tool uses the existing client."""
        from bot.tools import handle_tool_call

        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value={"ok": "sent"})

        with patch("bot.gateway.imessage.get_gateway_client", return_value=mock_client):
            result = await handle_tool_call("imessage_send", {
                "to": "+14155551234",
                "message": "Test message",
            })

        assert "sent" in result.lower() or "imessage" in result.lower()

    @pytest.mark.asyncio
    async def test_imessage_send_tool_fallback_standalone(self):
        """When no gateway, tool creates a temporary client."""
        from bot.tools import handle_tool_call

        with patch("bot.gateway.imessage.get_gateway_client", return_value=None), \
             patch("bot.gateway.imessage.run_imessage_send", new_callable=AsyncMock, return_value="sent ok") as mock_send:
            result = await handle_tool_call("imessage_send", {
                "to": "+14155551234",
                "message": "Test",
            })

        mock_send.assert_called_once_with(to="+14155551234", message="Test")
        assert result == "sent ok"
