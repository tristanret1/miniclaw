# Gateway Exchange Refactor — Design Spec

## Goal

Refactor the messaging architecture from "each channel directly calls LLM" to a centralized Gateway (exchange) pattern. Channels become thin adapters that only handle transport (receive/send); the Gateway handles routing, agent selection, and LLM orchestration.

## Current Problem

Every channel (feishu, sms, imessage, discord, cron) independently:
- Parses messages and builds `user_content`
- Resolves which agent to use
- Calls `llm.reply()` or `llm.stream()` directly
- Handles reply delivery with channel-specific logic

This duplicates routing/orchestration logic across 5+ files and makes adding new channels require copying the same boilerplate.

## Architecture

```
                    ┌──────────────────────────────────────────┐
                    │            Gateway (Exchange)             │
                    │                                          │
InboundMessage ───→ │  resolve_agent() → LLM → deliver_reply  │
      ↑             │       ↑                       │         │
      │             │  on_chunk streaming (optional) │         │
      │             └──────────────────────────────────────────┘
      │                         ↑                    │
 ┌────┴──────┐            ┌─────┴─────┐        ┌────┴──────┐
 │  Channel  │            │  Agent    │        │  Channel  │
 │  Adapter  │ (inbound)  │  Registry │        │  Adapter  │ (outbound)
 │           │            └───────────┘        │           │
 │ discord   │                                 │ discord   │
 │ feishu    │                                 │ feishu    │
 │ sms       │                                 │ sms       │
 │ imessage  │                                 │ imessage  │
 │ cron      │                                 │ cron      │
 └───────────┘                                 └───────────┘
```

## Data Model

### InboundMessage

Standardized message that all adapters produce:

```python
@dataclass
class InboundMessage:
    channel: str           # "discord", "feishu", "sms", "imessage", "cron"
    session_key: str       # adapter generates this (e.g. "feishu:chat_id:sender_id")
    text: str              # plain text content
    image_urls: list[str]  # image attachments
    reply_ctx: dict        # adapter-specific context for replying:
                           #   discord: {message, channel_obj}
                           #   feishu: {chat_id, message_id}
                           #   sms: {phone_number}
                           #   imessage: {handle}
                           #   cron: {job, delivery_channel, target_id}
```

## ChannelAdapter Interface

```python
class ChannelAdapter(ABC):
    name: str              # "feishu", "discord", "sms", "imessage"
    supports_streaming: bool = False

    @abstractmethod
    async def start(self, gateway: Gateway) -> None:
        """Start the adapter. Store gateway reference for submitting messages."""

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown."""

    @abstractmethod
    async def send(self, reply_ctx: dict, text: str) -> str:
        """Send a complete reply. Returns 'ok' or error string."""

    async def send_chunk(self, reply_ctx: dict, chunk: str, done: bool) -> None:
        """Optional: send a streaming chunk. Only called if supports_streaming=True."""
        pass
```

## Gateway Core

```python
class Gateway:
    _adapters: dict[str, ChannelAdapter]
    _agents: dict[str, Agent]          # agent_name → Agent
    _channel_agent_map: dict[str, str] # channel_name → agent_name (from config)

    async def handle(self, msg: InboundMessage) -> None:
        """Central message handler — called by adapters."""
        agent_name = self._channel_agent_map.get(msg.channel, "default")
        agent = self._agents.get(agent_name)
        adapter = self._adapters[msg.channel]
        content = build_user_content(msg.text, msg.image_urls)

        if adapter.supports_streaming:
            chunks = []
            async for chunk in llm.stream(msg.session_key, content, agent=agent):
                chunks.append(chunk)
                await adapter.send_chunk(msg.reply_ctx, chunk, done=False)
            await adapter.send_chunk(msg.reply_ctx, "", done=True)
        else:
            reply = await llm.reply(msg.session_key, content, agent=agent)
            if reply.strip():
                await adapter.send(msg.reply_ctx, reply)

    def get_adapter(self, name: str) -> ChannelAdapter | None:
        """Get adapter by name. Used by cron for delivery."""
        return self._adapters.get(name)
```

## Agent Routing

Config-driven mapping in `config.yaml`:

```yaml
gateway:
  feishu:
    enabled: true
    agent: feishu          # uses workspace_feishu/ (卡皮巴拉)
  sms:
    enabled: true
    agent: default         # uses workspace/
  imessage:
    enabled: true
    agent: default
  discord:
    agent: default         # DB agents override this per-bot
```

Each channel config gets an `agent` field. Gateway reads this at startup and builds the mapping. If `agent` is empty or missing, defaults to `"default"`.

Agent resolution:
1. Load agents from DB (existing `load_agents_async`)
2. For channels with workspace-based agents (feishu), create Agent from `workspace_{name}/`
3. Store all in `_agents` dict

## Adapter Implementations

### FeishuAdapter
- `start()`: init lark-oapi WS client in daemon thread, register event handler
- Inbound: `_on_message_receive` → parse text, strip bot mention, build `InboundMessage` → `gateway.handle()`
- `send()`: call `im.v1.message.acreate` (for cron delivery) or `im.v1.message.areply`
- `supports_streaming = False`

### DiscordAdapter
- `start()`: create discord.py bot, register `on_message`
- Inbound: extract text/images, build `InboundMessage` → `gateway.handle()`
- `send()`: `message.reply()` or `channel.send()`
- `send_chunk()`: edit message progressively with cursor indicator
- `supports_streaming = True`

### SMSAdapter
- `start()`: start aiohttp webhook server
- Inbound: parse Twilio POST → `InboundMessage` → `gateway.handle()`
- `send()`: call Twilio API
- `supports_streaming = False`

### IMessageAdapter
- `start()`: spawn imsg subprocess, register notification handler
- Inbound: parse incoming → `InboundMessage` → `gateway.handle()`
- `send()`: call imsg send
- `supports_streaming = False`

### CronAdapter (virtual)
- Not a real inbound adapter — cron scheduler constructs `InboundMessage` when a job fires
- Uses `gateway.get_adapter(delivery_channel).send()` for delivery
- Or submits to `gateway.handle()` which does LLM + delivery in one shot

## File Structure

| Current | After Refactor | Responsibility |
|---------|---------------|----------------|
| `bot/client.py` (700+ lines, Discord + LLM) | `bot/channel/discord.py` | Discord adapter (transport only) |
| `bot/gateway/feishu.py` | `bot/channel/feishu.py` | Feishu adapter (transport only) |
| `bot/gateway/sms.py` | `bot/channel/sms.py` | SMS adapter (transport only) |
| `bot/gateway/imessage.py` | `bot/channel/imessage.py` | iMessage adapter (transport only) |
| (new) | `bot/gateway.py` | Gateway exchange core |
| (new) | `bot/channel/__init__.py` | ChannelAdapter ABC + InboundMessage |
| `bot/services/cron.py` (delivery logic) | `bot/services/cron.py` (uses gateway) | Cron submits to gateway |
| `bot/gateway/status.py` | `bot/channel/status.py` | Status tracker (moves with adapters) |
| `bot/gateway/heartbeat.py` | `bot/channel/heartbeat.py` | Heartbeat (moves with adapters) |
| `bot/gateway/api.py` | `bot/channel/api.py` | API gateway (moves with adapters) |

## Startup Flow

```python
# main.py
async def main():
    agents = await load_agents_async()
    gateway = Gateway(agents, config)

    if feishu_enabled:
        gateway.register(FeishuAdapter())
    if sms_enabled:
        gateway.register(SMSAdapter())
    if discord_enabled:
        gateway.register(DiscordAdapter(bot_token))
    # etc.

    await gateway.start()   # starts all registered adapters
    # gateway.start() runs until cancelled
```

## What Doesn't Change

- `bot/llm.py` — Gateway calls it, interface unchanged
- `bot/processor.py` — stream processor, unchanged
- `bot/provider/` — LLM providers, unchanged
- `bot/storage/` — session/memory, unchanged
- `bot/tools/` — tool definitions, unchanged
- `bot/agent.py` — agent loading, unchanged
- `bot/audio/` — audio utilities, unchanged
- `bot/skills.py` — skill system, unchanged

## Migration Strategy

Implement incrementally:
1. Create `bot/channel/__init__.py` with ABC + InboundMessage
2. Create `bot/gateway.py` with Gateway core
3. Migrate one adapter at a time (feishu first — simplest, already in this session)
4. Each migration: extract transport logic into adapter, remove LLM calls, wire to gateway
5. Discord last (most complex — streaming, slash commands, debouncing)
6. Update cron to use gateway for delivery
7. Update main.py startup
