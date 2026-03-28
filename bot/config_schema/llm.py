from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnthropicProviderConfig:
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096


@dataclass(frozen=True)
class CodexProviderConfig:
    model: str = "gpt-5.3-codex"
    max_tokens: int = 4096


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "anthropic"
    max_history: int = 50
    tools_enabled: bool = False
    anthropic: AnthropicProviderConfig = field(default_factory=AnthropicProviderConfig)
    codex: CodexProviderConfig = field(default_factory=CodexProviderConfig)
