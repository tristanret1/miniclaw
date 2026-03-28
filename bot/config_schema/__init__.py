"""
config_schema — frozen dataclasses defining the shape of config.yaml.

All non-sensitive settings live here with their defaults. Sensitive values
(tokens, API keys, passwords) remain in environment variables / .env.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from bot.config_schema.llm import LLMConfig, AnthropicProviderConfig, CodexProviderConfig
from bot.config_schema.discord import DiscordConfig, AutoReplyConfig, StreamConfig
from bot.config_schema.gateway import (
    GatewayConfig,
    VoiceConfig,
    VolcengineConfig,
    SMSConfig,
    IMessageConfig,
    HeartbeatConfig,
)
from bot.config_schema.storage import StorageConfig, SQLiteConfig
from bot.config_schema.services import (
    ServicesConfig,
    GoogleCalendarConfig,
    CronConfig,
    HealthConfig,
    TimeoutConfig,
)

__all__ = [
    "AppConfig",
    "_build_dataclass",
    # llm
    "LLMConfig",
    "AnthropicProviderConfig",
    "CodexProviderConfig",
    # discord
    "DiscordConfig",
    "AutoReplyConfig",
    "StreamConfig",
    # gateway
    "GatewayConfig",
    "VoiceConfig",
    "VolcengineConfig",
    "SMSConfig",
    "IMessageConfig",
    "HeartbeatConfig",
    # storage
    "StorageConfig",
    "SQLiteConfig",
    # services
    "ServicesConfig",
    "GoogleCalendarConfig",
    "CronConfig",
    "HealthConfig",
    "TimeoutConfig",
]


def _build_dataclass(cls: type, raw: dict) -> Any:
    """Recursively build a frozen dataclass from a nested dict.

    For each field in *cls*:
    - If the field type is itself a dataclass and the corresponding value in
      *raw* is a dict, recurse.
    - If the field type is ``tuple`` and the value is a list, convert.
    - Otherwise assign the raw value directly (or use the field default when
      the key is absent from *raw*).
    """
    if not dataclasses.is_dataclass(cls):
        raise TypeError(f"{cls} is not a dataclass")

    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.name not in raw:
            # Let the dataclass use its own default / default_factory.
            continue
        value = raw[f.name]
        field_type = f.type  # may be a string annotation or actual type

        # Resolve string annotations (from `from __future__ import annotations`)
        if isinstance(field_type, str):
            import sys
            ns = sys.modules[cls.__module__].__dict__
            try:
                field_type = eval(field_type, ns)  # noqa: S307
            except Exception:
                field_type = None

        if field_type is not None and dataclasses.is_dataclass(field_type) and isinstance(value, dict):
            kwargs[f.name] = _build_dataclass(field_type, value)
        elif field_type is tuple and isinstance(value, list):
            kwargs[f.name] = tuple(value)
        else:
            kwargs[f.name] = value

    return cls(**kwargs)


@dataclasses.dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration composed from sub-configs."""

    llm: LLMConfig = dataclasses.field(default_factory=LLMConfig)
    discord: DiscordConfig = dataclasses.field(default_factory=DiscordConfig)
    gateway: GatewayConfig = dataclasses.field(default_factory=GatewayConfig)
    storage: StorageConfig = dataclasses.field(default_factory=StorageConfig)
    services: ServicesConfig = dataclasses.field(default_factory=ServicesConfig)

    @classmethod
    def from_dict(cls, raw: dict) -> "AppConfig":
        """Build an AppConfig from a nested dict (e.g. parsed from config.yaml)."""
        return _build_dataclass(cls, raw)
