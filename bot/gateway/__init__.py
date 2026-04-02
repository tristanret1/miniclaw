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
        self._adapters: dict[str, list[ChannelAdapter]] = {}  # channel_name → [adapters]
        self._agents: dict[str, object] = {}       # agent_name → Agent
        self._channel_agent: dict[str, str] = {}    # channel_name → agent_name

    def register_adapter(self, adapter: ChannelAdapter) -> None:
        """Register a channel adapter. Multiple adapters per channel are supported."""
        self._adapters.setdefault(adapter.name, []).append(adapter)
        agent_name = getattr(getattr(adapter, "_agent", None), "name", "?")
        log.info("registered adapter: %s (agent=%s, total=%d for channel)",
                 adapter.name, agent_name, len(self._adapters[adapter.name]))

    def register_agent(self, name: str, agent) -> None:
        """Register an agent by name."""
        self._agents[name] = agent

    def set_channel_agent(self, channel: str, agent_name: str) -> None:
        """Map a channel to an agent name."""
        self._channel_agent[channel] = agent_name

    def get_adapter(self, name: str) -> ChannelAdapter | None:
        """Get first adapter by channel name."""
        adapters = self._adapters.get(name, [])
        return adapters[0] if adapters else None

    def _get_ready_adapter(self, name: str, agent_name: str = "") -> ChannelAdapter | None:
        """Get a ready adapter for a channel.

        If agent_name is given, prefer the adapter bound to that agent.
        Otherwise return the first ready one.
        """
        adapters = self._adapters.get(name, [])

        def _is_ready(adapter: ChannelAdapter) -> bool:
            bot = getattr(adapter, "_bot", None)
            if bot and hasattr(bot, "is_ready"):
                return bot.is_ready()
            return True

        # Try matching agent first
        if agent_name:
            for adapter in adapters:
                a = getattr(adapter, "_agent", None)
                if a and getattr(a, "name", "") == agent_name and _is_ready(adapter):
                    return adapter

        # Fallback: first ready adapter
        for adapter in adapters:
            if _is_ready(adapter):
                return adapter
        return None

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
        agent_name = getattr(agent, "name", "default") if agent else "default"

        # Determine which adapter delivers the reply
        delivery = msg.delivery_channel or msg.channel
        adapter = self._get_ready_adapter(delivery, msg.reply_ctx.get("agent", ""))
        if not adapter:
            log.error("no adapter for delivery channel=%s (source=%s)", delivery, msg.channel)
            return

        log.info("handle: source=%s delivery=%s session=%s agent=%s streaming=%s reply_ctx_keys=%s",
                 msg.channel, delivery, msg.session_key, agent_name,
                 adapter.supports_streaming and not msg.delivery_channel,
                 list(msg.reply_ctx.keys()))

        content = build_user_content(msg.text, msg.image_urls or None)

        # Only use streaming when the adapter is also the source (real-time chat).
        # Cross-channel delivery (cron/heartbeat → discord) always uses non-streaming.
        use_streaming = adapter.supports_streaming and not msg.delivery_channel

        if use_streaming:
            async for chunk in llm.stream(msg.session_key, content, agent=agent):
                await adapter.send_chunk(msg.reply_ctx, chunk, done=False)
            await adapter.send_chunk(msg.reply_ctx, "", done=True)
            log.info("handle: streaming complete for session=%s", msg.session_key)
        else:
            reply = await llm.reply(msg.session_key, content, agent=agent)
            log.info("handle: reply len=%d for session=%s", len(reply), msg.session_key)
            if reply.strip():
                result = await adapter.send(msg.reply_ctx, reply)
                log.info("handle: send result=%s for session=%s", result, msg.session_key)
            else:
                log.warning("handle: empty reply for session=%s", msg.session_key)

    async def deliver(self, channel: str, reply_ctx: dict, text: str) -> str:
        """Deliver a message through a specific channel adapter. Used by cron/heartbeat."""
        adapter = self._get_ready_adapter(channel, reply_ctx.get("agent", ""))
        if not adapter:
            return f"Error: no ready adapter for channel '{channel}'"
        return await adapter.send(reply_ctx, text)

    async def start(self) -> None:
        """Start all registered adapters."""
        total = 0
        for adapters in self._adapters.values():
            for adapter in adapters:
                await adapter.start(self)
                total += 1
        log.info("gateway started with %d adapter(s) across %s",
                 total, ", ".join(f"{k}({len(v)})" for k, v in self._adapters.items()))

    async def stop(self) -> None:
        """Stop all adapters."""
        for adapters in self._adapters.values():
            for adapter in adapters:
                await adapter.stop()
