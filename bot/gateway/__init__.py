"""Gateway exchange — central message router."""

from __future__ import annotations

from bot import llm
from bot.channel import ChannelAdapter, InboundMessage
from bot.logger import get_logger
from bot.message import build_user_content

log = get_logger("gateway")

# Module-level singleton
_gateway: Gateway | None = None


def get_gateway() -> Gateway | None:
    """Return the singleton Gateway instance."""
    return _gateway


def set_gateway(gw: Gateway) -> None:
    """Set the singleton Gateway instance."""
    global _gateway
    _gateway = gw


class Gateway:
    """Central exchange: receives InboundMessage, routes to LLM, delivers reply."""

    def __init__(self):
        self._adapters: dict[str, ChannelAdapter] = {}
        self._agents: dict[str, object] = {}       # agent_name → Agent
        self._channel_agent: dict[str, str] = {}    # channel_name → agent_name

    def register_adapter(self, adapter: ChannelAdapter) -> None:
        """Register a channel adapter."""
        self._adapters[adapter.name] = adapter

    def register_agent(self, name: str, agent) -> None:
        """Register an agent by name."""
        self._agents[name] = agent

    def set_channel_agent(self, channel: str, agent_name: str) -> None:
        """Map a channel to an agent name."""
        self._channel_agent[channel] = agent_name

    def get_adapter(self, name: str) -> ChannelAdapter | None:
        """Get adapter by name."""
        return self._adapters.get(name)

    def get_agent(self, channel: str):
        """Resolve the agent for a channel."""
        agent_name = self._channel_agent.get(channel, "default")
        return self._agents.get(agent_name)

    async def handle(self, msg: InboundMessage) -> None:
        """Central handler — called by adapters or schedulers.

        If msg.delivery_channel is set, the reply is delivered through that
        adapter instead of the source channel. This supports cron/heartbeat
        where the source is virtual but delivery goes to a real channel.
        """
        agent = self.get_agent(msg.channel)

        # Determine which adapter delivers the reply
        delivery = msg.delivery_channel or msg.channel
        adapter = self._adapters.get(delivery)
        if not adapter:
            log.error("no adapter for delivery channel=%s (source=%s)", delivery, msg.channel)
            return

        content = build_user_content(msg.text, msg.image_urls or None)

        # Only use streaming when the adapter is also the source (real-time chat).
        # Cross-channel delivery (cron/heartbeat → discord) always uses non-streaming.
        use_streaming = adapter.supports_streaming and not msg.delivery_channel

        if use_streaming:
            async for chunk in llm.stream(msg.session_key, content, agent=agent):
                await adapter.send_chunk(msg.reply_ctx, chunk, done=False)
            await adapter.send_chunk(msg.reply_ctx, "", done=True)
        else:
            reply = await llm.reply(msg.session_key, content, agent=agent)
            if reply.strip():
                await adapter.send(msg.reply_ctx, reply)

    async def deliver(self, channel: str, reply_ctx: dict, text: str) -> str:
        """Deliver a message through a specific channel adapter. Used by cron."""
        adapter = self._adapters.get(channel)
        if not adapter:
            return f"Error: no adapter for channel '{channel}'"
        return await adapter.send(reply_ctx, text)

    async def start(self) -> None:
        """Start all registered adapters."""
        for adapter in self._adapters.values():
            await adapter.start(self)
        log.info("gateway started with %d adapter(s): %s",
                 len(self._adapters), ", ".join(self._adapters.keys()))

    async def stop(self) -> None:
        """Stop all adapters."""
        for adapter in self._adapters.values():
            await adapter.stop()
