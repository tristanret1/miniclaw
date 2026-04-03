"""Channel adapter base types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class InboundMessage:
    """Standardized message from any channel into the Gateway."""
    channel: str           # source: "discord", "feishu", "sms", "imessage", "cron", "heartbeat"
    session_key: str
    text: str
    image_urls: list[str] = field(default_factory=list)
    reply_ctx: dict = field(default_factory=dict)
    delivery_channel: str = ""  # if set, reply goes to this adapter instead of source channel
    agent_override: str = ""   # if set, use this agent instead of channel→agent mapping


class ChannelAdapter(ABC):
    """Base class for channel adapters (transport only)."""

    name: str = ""
    supports_streaming: bool = False

    @abstractmethod
    async def start(self, gateway) -> None:
        """Start the adapter. Store gateway ref for submitting inbound messages."""

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown."""

    @abstractmethod
    async def send(self, reply_ctx: dict, text: str) -> str:
        """Send a complete reply. Returns 'ok' or error string."""

    async def send_chunk(self, reply_ctx: dict, chunk: str, done: bool) -> None:
        """Optional: streaming chunk. Only called if supports_streaming=True."""
        pass
