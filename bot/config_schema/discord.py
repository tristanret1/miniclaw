from dataclasses import dataclass, field


@dataclass(frozen=True)
class AutoReplyConfig:
    enabled: bool = False
    channels: list = field(default_factory=list)
    chance: float = 0.1
    keywords: list = field(default_factory=list)


@dataclass(frozen=True)
class StreamConfig:
    first_chunk_min_chars: int = 5
    first_chunk_timeout: float = 0.3
    edit_interval: float = 0.1
    edit_min_chars: int = 50
    edit_force_chars: int = 100
    max_message_length: int = 2000


@dataclass(frozen=True)
class DiscordConfig:
    auto_reply: AutoReplyConfig = field(default_factory=AutoReplyConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
