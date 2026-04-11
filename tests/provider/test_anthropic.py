"""Tests for bot.provider.anthropic — AnthropicProvider HTTP/SSE logic."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.provider.anthropic import AnthropicProvider


class TestBuildBody:
    def test_with_tools(self):
        provider = AnthropicProvider(model="claude-test")
        tools = [{"name": "exec", "description": "run", "input_schema": {}}]
        body = provider._build_body(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=tools,
            max_tokens=1024,
            stream=True,
        )
        assert body["model"] == "claude-test"
        assert body["stream"] is True
        # tools 最后一个应带 cache_control（稳定内容，适合缓存）
        assert len(body["tools"]) == 1
        assert body["tools"][0]["name"] == "exec"
        assert body["tools"][0]["cache_control"] == {"type": "ephemeral"}
        assert body["max_tokens"] == 1024

    def test_without_tools(self):
        provider = AnthropicProvider(model="claude-test")
        body = provider._build_body(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=None,
            max_tokens=4096,
            stream=False,
        )
        assert "tools" not in body
        assert body["stream"] is False


class TestHeaders:
    def test_format(self):
        provider = AnthropicProvider(model="claude-test")
        headers = provider._headers("test-token")
        assert headers["Authorization"] == "Bearer test-token"
        assert "anthropic-version" in headers
        assert headers["Content-Type"] == "application/json"


class TestGetAccessToken:
    def test_no_credentials_raises(self, monkeypatch):
        provider = AnthropicProvider(model="claude-test")
        monkeypatch.setattr("bot.provider.anthropic.load_credentials", lambda: None)
        with pytest.raises(RuntimeError, match="Not authenticated"):
            provider._get_access_token()

    def test_returns_token(self, fake_credentials):
        provider = AnthropicProvider(model="claude-test")
        token = provider._get_access_token()
        assert token == "fake-access-token"


class TestCall:
    async def test_success(self, fake_credentials):
        provider = AnthropicProvider(model="claude-test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "hello"}],
            "stop_reason": "end_turn",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        provider._http = mock_client

        result = await provider.call(
            messages=[{"role": "user", "content": "hi"}],
            system="test",
        )
        assert result["content"][0]["text"] == "hello"

    async def test_401_triggers_refresh(self, fake_credentials):
        provider = AnthropicProvider(model="claude-test")

        # First call returns 401, second returns 200
        resp_401 = MagicMock()
        resp_401.status_code = 401

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {"content": [], "stop_reason": "end_turn"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[resp_401, resp_200])
        mock_client.is_closed = False
        provider._http = mock_client

        with patch("bot.provider.anthropic.refresh_token") as mock_refresh:
            mock_refresh.return_value = {"access_token": "new-token"}
            result = await provider.call(
                messages=[{"role": "user", "content": "hi"}],
                system="test",
            )
            mock_refresh.assert_called_once()

    async def test_non_200_raises(self, fake_credentials):
        provider = AnthropicProvider(model="claude-test")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        provider._http = mock_client

        with pytest.raises(RuntimeError, match="Claude API error.*500"):
            await provider.call(
                messages=[{"role": "user", "content": "hi"}],
                system="test",
            )


class TestGetClient:
    async def test_creates_client(self):
        provider = AnthropicProvider(model="claude-test")
        client = provider._get_client()
        assert client is not None
        # Same client on second call
        assert provider._get_client() is client
        # Cleanup
        await client.aclose()
