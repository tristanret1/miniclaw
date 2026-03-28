"""Provider registry and factory."""

from bot.provider.base import BaseProvider
from bot.provider.anthropic import AnthropicProvider
from bot.provider.codex import CodexProvider

_PROVIDERS: dict[str, type[BaseProvider]] = {
    "anthropic": AnthropicProvider,
    "codex": CodexProvider,
}


def get_provider(provider_id: str, model: str) -> BaseProvider:
    """Get a Provider instance by provider_id and model."""
    cls = _PROVIDERS.get(provider_id)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_id}")
    return cls(model=model)


def get_default_provider() -> BaseProvider:
    """Get the default provider based on config."""
    from bot.config import get_config
    cfg = get_config()
    if cfg.llm.provider == "codex":
        return get_provider("codex", cfg.llm.codex.model)
    return get_provider("anthropic", cfg.llm.anthropic.model)
