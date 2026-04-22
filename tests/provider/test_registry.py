"""Tests for bot.provider — provider registry and factory."""

import pytest

from bot.provider import get_provider, get_default_provider
from bot.provider.anthropic import AnthropicProvider
from bot.provider.codex import CodexProvider
from bot.provider.kimi import KimiProvider


class TestBaseProvider:
    async def test_close_noop_when_no_client(self):
        provider = get_provider("anthropic", "claude-test")
        await provider.close()
        assert provider._http is None

    async def test_close_closes_client(self):
        import httpx
        provider = get_provider("anthropic", "claude-test")
        provider._http = httpx.AsyncClient()
        await provider.close()
        assert provider._http is None


class TestProviderRegistry:
    def test_get_anthropic_provider(self):
        provider = get_provider("anthropic", "claude-test")
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "claude-test"

    def test_get_codex_provider(self):
        provider = get_provider("codex", "gpt-5.3-codex")
        assert isinstance(provider, CodexProvider)
        assert provider.model == "gpt-5.3-codex"

    def test_get_kimi_provider(self):
        provider = get_provider("kimi", "kimi-latest")
        assert isinstance(provider, KimiProvider)
        assert provider.model == "kimi-latest"
        assert provider.API_URL == "https://api.moonshot.cn/v1/chat/completions"
        assert provider.ENV_KEY == "KIMI_API_KEY"

    def test_get_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("openai", "gpt-4")

    def test_get_default_provider_anthropic(self):
        provider = get_default_provider()
        assert isinstance(provider, AnthropicProvider)

    def test_get_default_provider_codex(self, monkeypatch):
        from bot.config import reset_config
        from bot.config_schema import AppConfig, LLMConfig, CodexConfig
        import bot.config as cfg_mod
        codex_cfg = AppConfig.from_dict({"llm": {"provider": "codex", "codex": {"model": "gpt-5.3-codex"}}})
        monkeypatch.setattr(cfg_mod, "_config", codex_cfg)
        try:
            provider = get_default_provider()
            assert isinstance(provider, CodexProvider)
        finally:
            reset_config()

    def test_get_default_provider_kimi(self, monkeypatch):
        from bot.config import reset_config
        from bot.config_schema import AppConfig
        import bot.config as cfg_mod
        kimi_cfg = AppConfig.from_dict({"llm": {"provider": "kimi", "kimi": {"model": "kimi-latest"}}})
        monkeypatch.setattr(cfg_mod, "_config", kimi_cfg)
        try:
            provider = get_default_provider()
            assert isinstance(provider, KimiProvider)
            assert provider.model == "kimi-latest"
        finally:
            reset_config()
