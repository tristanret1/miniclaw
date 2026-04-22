"""Tests for bot.provider.kimi — KimiProvider (Kimi Code subscription, Anthropic Messages wire format)."""

import pytest

from bot.provider.kimi import ANTHROPIC_API_VERSION, KIMI_USER_AGENT, KimiProvider


class TestBuildBody:
    def test_with_tools_and_system(self):
        provider = KimiProvider(model="kimi-for-coding")
        tools = [{"name": "exec", "description": "run", "input_schema": {}}]
        body = provider._build_body(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=tools,
            max_tokens=1024,
            stream=True,
        )
        assert body["model"] == "kimi-for-coding"
        assert body["stream"] is True
        assert body["max_tokens"] == 1024
        assert body["system"] == "sys"
        assert body["tools"] == tools
        # Kimi Code does not need cache_control breakpoints — pass tools through untouched.
        assert "cache_control" not in body["tools"][0]

    def test_without_tools_or_system(self):
        provider = KimiProvider(model="kimi-for-coding")
        body = provider._build_body(
            messages=[{"role": "user", "content": "hi"}],
            system="",
            tools=None,
            max_tokens=4096,
            stream=False,
        )
        assert "tools" not in body
        assert "system" not in body
        assert body["stream"] is False


class TestHeaders:
    def test_uses_api_key_and_claude_code_user_agent(self, monkeypatch):
        monkeypatch.setenv("KIMI_API_KEY", "sk-test-kimi")
        provider = KimiProvider(model="kimi-for-coding")
        headers = provider._headers()
        assert headers["x-api-key"] == "sk-test-kimi"
        assert headers["anthropic-version"] == ANTHROPIC_API_VERSION
        assert headers["User-Agent"] == KIMI_USER_AGENT
        assert headers["Content-Type"] == "application/json"
        # Kimi uses x-api-key (not Bearer) — no Authorization header.
        assert "Authorization" not in headers


class TestGetApiKey:
    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("KIMI_API_KEY", raising=False)
        provider = KimiProvider(model="kimi-for-coding")
        with pytest.raises(RuntimeError, match="KIMI_API_KEY not set"):
            provider._get_api_key()

    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv("KIMI_API_KEY", "sk-abc")
        provider = KimiProvider(model="kimi-for-coding")
        assert provider._get_api_key() == "sk-abc"


class TestApiUrlFromConfig:
    def test_reads_url_from_config(self):
        provider = KimiProvider(model="kimi-for-coding")
        assert provider.API_URL == "https://api.kimi.com/coding/v1/messages"


class TestRefreshAuth:
    async def test_noop(self):
        provider = KimiProvider(model="kimi-for-coding")
        await provider.refresh_auth()  # Should not raise.
