"""Tests for bot.provider — provider registry and factory."""

import pytest

from bot.provider import get_provider, get_default_provider
from bot.provider.anthropic import AnthropicProvider
from bot.provider.codex import CodexProvider


class TestProviderRegistry:
    def test_get_anthropic_provider(self):
        provider = get_provider("anthropic", "claude-test")
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "claude-test"

    def test_get_codex_provider(self):
        provider = get_provider("codex", "gpt-5.3-codex")
        assert isinstance(provider, CodexProvider)
        assert provider.model == "gpt-5.3-codex"

    def test_get_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("openai", "gpt-4")

    def test_get_default_provider_anthropic(self):
        provider = get_default_provider()
        assert isinstance(provider, AnthropicProvider)

    def test_get_default_provider_codex(self, monkeypatch):
        import bot.config
        monkeypatch.setattr(bot.config, "PROVIDER", "codex")
        monkeypatch.setattr(bot.config, "CODEX_MODEL", "gpt-5.3-codex")
        provider = get_default_provider()
        assert isinstance(provider, CodexProvider)
