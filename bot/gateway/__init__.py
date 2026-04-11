"""Gateway exchange — central message router.

Single-agent version: all channels route to the one Peter agent.
"""

from __future__ import annotations

from bot import llm
from bot.channel import ChannelAdapter, InboundMessage
from bot.logger import get_logger
from bot.message import build_user_content

log = get_logger("gateway")

# Module-level singleton
_gateway: Gateway | None = None


def get_gateway() -> Gateway | None:
    return _gateway


def set_gateway(gw: Gateway) -> None:
    global _gateway
    _gateway = gw


class Gateway:
    """Central exchange: receives InboundMessage, routes to the single agent, delivers reply."""

    def __init__(self, agent):
        self._agent = agent
        self._adapters: dict[str, list[ChannelAdapter]] = {}  # channel_name → [adapters]

    def register_adapter(self, adapter: ChannelAdapter) -> None:
        self._adapters.setdefault(adapter.name, []).append(adapter)
        log.info("registered adapter: %s", adapter.name)

    def get_adapter(self, name: str) -> ChannelAdapter | None:
        adapters = self._adapters.get(name, [])
        return adapters[0] if adapters else None

    def _get_ready_adapter(self, name: str) -> ChannelAdapter | None:
        adapters = self._adapters.get(name, [])
        for adapter in adapters:
            bot = getattr(adapter, "_bot", None)
            if bot and hasattr(bot, "is_ready") and not bot.is_ready():
                continue
            return adapter
        return None

    async def handle(self, msg: InboundMessage) -> None:
        """Central handler — called by adapters or schedulers."""
        delivery = msg.delivery_channel or msg.channel
        adapter = self._get_ready_adapter(delivery)
        if not adapter:
            log.error("no adapter for delivery channel=%s (source=%s)", delivery, msg.channel)
            return

        log.info("handle: source=%s delivery=%s session=%s streaming=%s",
                 msg.channel, delivery, msg.session_key,
                 adapter.supports_streaming and not msg.delivery_channel)

        content = build_user_content(msg.text, msg.image_urls or None)
        use_streaming = adapter.supports_streaming and not msg.delivery_channel

        if use_streaming:
            async for chunk in llm.stream(msg.session_key, content, agent=self._agent):
                await adapter.send_chunk(msg.reply_ctx, chunk, done=False)
            await adapter.send_chunk(msg.reply_ctx, "", done=True)
        else:
            reply = await llm.reply(msg.session_key, content, agent=self._agent)
            if reply.strip():
                await adapter.send(msg.reply_ctx, reply)
            else:
                log.warning("handle: empty reply for session=%s", msg.session_key)

    async def deliver(self, channel: str, reply_ctx: dict, text: str) -> str:
        """Deliver a message through a specific channel adapter."""
        adapter = self._get_ready_adapter(channel)
        if not adapter:
            return f"Error: no ready adapter for channel '{channel}'"
        return await adapter.send(reply_ctx, text)

    async def start(self) -> None:
        total = 0
        for adapters in self._adapters.values():
            for adapter in adapters:
                await adapter.start(self)
                total += 1
        log.info("gateway started with %d adapter(s)", total)

    async def stop(self) -> None:
        for adapters in self._adapters.values():
            for adapter in adapters:
                await adapter.stop()
