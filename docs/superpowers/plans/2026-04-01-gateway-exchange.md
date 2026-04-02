# Gateway Exchange Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor messaging from "each channel calls LLM directly" to a centralized Gateway exchange with thin channel adapters.

**Architecture:** A `Gateway` class acts as the exchange — it receives `InboundMessage` from channel adapters, resolves the agent, calls LLM (streaming or non-streaming), and delivers the reply back through the adapter. Each adapter implements `ChannelAdapter` ABC and only handles transport.

**Tech Stack:** Python 3.10+, asyncio, existing discord.py / lark-oapi / aiohttp

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `bot/channel/__init__.py` | `ChannelAdapter` ABC + `InboundMessage` dataclass |
| Create | `bot/gateway.py` | `Gateway` exchange core |
| Create | `bot/channel/feishu.py` | Feishu adapter (transport only) |
| Create | `bot/channel/sms.py` | SMS adapter (transport only) |
| Create | `bot/channel/discord.py` | Discord adapter (transport + streaming) |
| Move | `bot/gateway/imessage.py` → `bot/channel/imessage.py` | iMessage adapter |
| Move | `bot/gateway/heartbeat.py` → `bot/channel/heartbeat.py` | Heartbeat |
| Move | `bot/gateway/api.py` → `bot/channel/api.py` | API gateway |
| Move | `bot/gateway/status.py` → `bot/channel/status.py` | Status tracker |
| Modify | `bot/services/cron.py` | Use gateway for delivery |
| Modify | `main.py` | Wire up Gateway + adapters |
| Modify | `bot/config_schema.py` | Add `agent` field to channel configs |
| Delete | `bot/gateway/feishu.py` | Replaced by `bot/channel/feishu.py` |
| Delete | `bot/gateway/sms.py` | Replaced by `bot/channel/sms.py` |
| Create | `tests/test_gateway.py` | Gateway tests |
| Create | `tests/channel/test_feishu.py` | Feishu adapter tests |
| Create | `tests/channel/test_sms.py` | SMS adapter tests |

---

### Task 1: ChannelAdapter ABC + InboundMessage

**Files:**
- Create: `bot/channel/__init__.py`
- Create: `tests/channel/__init__.py`
- Create: `tests/channel/test_channel.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for channel base types."""
from bot.channel import InboundMessage, ChannelAdapter


class TestInboundMessage:
    def test_create(self):
        msg = InboundMessage(
            channel="test",
            session_key="test:123",
            text="hello",
            image_urls=[],
            reply_ctx={"id": "abc"},
        )
        assert msg.channel == "test"
        assert msg.text == "hello"

    def test_defaults(self):
        msg = InboundMessage(
            channel="test",
            session_key="test:123",
            text="hi",
        )
        assert msg.image_urls == []
        assert msg.reply_ctx == {}


class TestChannelAdapterABC:
    def test_cannot_instantiate(self):
        import pytest
        with pytest.raises(TypeError):
            ChannelAdapter()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/channel/test_channel.py -v`
Expected: FAIL — `bot.channel` does not exist

- [ ] **Step 3: Implement**

`bot/channel/__init__.py`:
```python
"""Channel adapter base types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class InboundMessage:
    """Standardized message from any channel into the Gateway."""
    channel: str           # "discord", "feishu", "sms", "imessage", "cron"
    session_key: str
    text: str
    image_urls: list[str] = field(default_factory=list)
    reply_ctx: dict = field(default_factory=dict)


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
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add bot/channel/__init__.py tests/channel/
git commit -m "feat: add ChannelAdapter ABC and InboundMessage dataclass"
```

---

### Task 2: Gateway exchange core

**Files:**
- Create: `bot/gateway.py`
- Create: `tests/test_gateway.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for Gateway exchange."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot.channel import InboundMessage, ChannelAdapter
from bot.gateway import Gateway


class FakeAdapter(ChannelAdapter):
    name = "fake"
    supports_streaming = False

    def __init__(self):
        self.sent = []
        self._gateway = None

    async def start(self, gateway):
        self._gateway = gateway

    async def stop(self):
        pass

    async def send(self, reply_ctx, text):
        self.sent.append((reply_ctx, text))
        return "ok"


class TestGateway:
    @patch("bot.gateway.llm")
    async def test_handle_non_streaming(self, mock_llm):
        mock_llm.reply = AsyncMock(return_value="hello back")
        adapter = FakeAdapter()
        gw = Gateway()
        gw.register_adapter(adapter)
        gw.register_agent("default", MagicMock())
        await adapter.start(gw)

        msg = InboundMessage(
            channel="fake",
            session_key="fake:123",
            text="hello",
            reply_ctx={"id": "msg1"},
        )
        await gw.handle(msg)

        assert len(adapter.sent) == 1
        assert adapter.sent[0][1] == "hello back"

    @patch("bot.gateway.llm")
    async def test_handle_empty_reply_not_sent(self, mock_llm):
        mock_llm.reply = AsyncMock(return_value="   ")
        adapter = FakeAdapter()
        gw = Gateway()
        gw.register_adapter(adapter)
        gw.register_agent("default", MagicMock())
        await adapter.start(gw)

        msg = InboundMessage(channel="fake", session_key="k", text="hi")
        await gw.handle(msg)
        assert len(adapter.sent) == 0

    def test_register_adapter(self):
        gw = Gateway()
        adapter = FakeAdapter()
        gw.register_adapter(adapter)
        assert gw.get_adapter("fake") is adapter

    def test_get_adapter_missing(self):
        gw = Gateway()
        assert gw.get_adapter("nope") is None
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement**

`bot/gateway.py`:
```python
"""Gateway exchange — central message router."""

from __future__ import annotations

from bot import llm
from bot.channel import ChannelAdapter, InboundMessage
from bot.logger import get_logger
from bot.message import build_user_content

log = get_logger("gateway")


class Gateway:
    """Central exchange: receives InboundMessage, routes to LLM, delivers reply."""

    def __init__(self):
        self._adapters: dict[str, ChannelAdapter] = {}
        self._agents: dict[str, object] = {}       # agent_name → Agent
        self._channel_agent: dict[str, str] = {}    # channel_name → agent_name

    def register_adapter(self, adapter: ChannelAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def register_agent(self, name: str, agent) -> None:
        self._agents[name] = agent

    def set_channel_agent(self, channel: str, agent_name: str) -> None:
        self._channel_agent[channel] = agent_name

    def get_adapter(self, name: str) -> ChannelAdapter | None:
        return self._adapters.get(name)

    def get_agent(self, channel: str):
        agent_name = self._channel_agent.get(channel, "default")
        return self._agents.get(agent_name)

    async def handle(self, msg: InboundMessage) -> None:
        """Central handler — called by adapters."""
        agent = self.get_agent(msg.channel)
        adapter = self._adapters.get(msg.channel)
        if not adapter:
            log.error("no adapter for channel=%s", msg.channel)
            return

        content = build_user_content(msg.text, msg.image_urls or None)

        if adapter.supports_streaming:
            buffer = []
            async for chunk in llm.stream(msg.session_key, content, agent=agent):
                buffer.append(chunk)
                await adapter.send_chunk(msg.reply_ctx, chunk, done=False)
            await adapter.send_chunk(msg.reply_ctx, "", done=True)
        else:
            reply = await llm.reply(msg.session_key, content, agent=agent)
            if reply.strip():
                await adapter.send(msg.reply_ctx, reply)

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

    async def deliver(self, channel: str, reply_ctx: dict, text: str) -> str:
        """Deliver a message through a specific channel adapter. Used by cron."""
        adapter = self._adapters.get(channel)
        if not adapter:
            return f"Error: no adapter for channel '{channel}'"
        return await adapter.send(reply_ctx, text)
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add bot/gateway.py tests/test_gateway.py
git commit -m "feat: add Gateway exchange core"
```

---

### Task 3: Feishu channel adapter

**Files:**
- Create: `bot/channel/feishu.py`
- Create: `tests/channel/test_feishu.py`
- Delete: `bot/gateway/feishu.py`

- [ ] **Step 1: Write tests**

Migrate existing `tests/gateway/test_feishu.py` tests to `tests/channel/test_feishu.py`, updating imports from `bot.gateway.feishu` to `bot.channel.feishu`.

- [ ] **Step 2: Implement `bot/channel/feishu.py`**

Extract from current `bot/gateway/feishu.py`:
- Keep all transport logic (WS client, send/reply, message parsing, dedup, bot info)
- Remove direct `llm.reply()` call — instead build `InboundMessage` and call `self._gateway.handle()`
- Implement `ChannelAdapter` interface (`start`, `stop`, `send`)
- Agent setup moves to `main.py` / gateway config

Key changes in `_process_feishu_message`:
```python
# OLD:
from bot import llm
reply_text = await llm.reply(session_key, user_content, agent=_feishu_agent)
if reply_text.strip():
    result = await _reply_feishu_message(message_id, reply_text)

# NEW:
msg = InboundMessage(
    channel="feishu",
    session_key=feishu_key(chat_id, sender_id),
    text=text,
    reply_ctx={"chat_id": chat_id, "message_id": message_id},
)
await self._gateway.handle(msg)
```

`send()` method:
```python
async def send(self, reply_ctx: dict, text: str) -> str:
    message_id = reply_ctx.get("message_id")
    chat_id = reply_ctx.get("chat_id")
    if message_id:
        result = await self._reply(message_id, text)
        if result == "ok":
            return result
    # Fallback to direct send
    return await self._send(chat_id, text)
```

- [ ] **Step 3: Delete `bot/gateway/feishu.py`**
- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add bot/channel/feishu.py tests/channel/test_feishu.py
git rm bot/gateway/feishu.py tests/gateway/test_feishu.py
git commit -m "refactor: migrate feishu to channel adapter pattern"
```

---

### Task 4: SMS channel adapter

**Files:**
- Create: `bot/channel/sms.py`
- Move: `tests/gateway/test_sms.py` → `tests/channel/test_sms.py`
- Delete: `bot/gateway/sms.py`

- [ ] **Step 1: Implement `bot/channel/sms.py`**

Same pattern as feishu: extract transport, replace `llm.reply()` with `gateway.handle()`.

`send()`: call Twilio API (currently `run_sms` from `bot/tools`).

- [ ] **Step 2: Update tests**
- [ ] **Step 3: Delete old file, run tests**
- [ ] **Step 4: Commit**

```bash
git commit -m "refactor: migrate sms to channel adapter pattern"
```

---

### Task 5: Move remaining gateway/ files to channel/

**Files:**
- Move: `bot/gateway/imessage.py` → `bot/channel/imessage.py`
- Move: `bot/gateway/heartbeat.py` → `bot/channel/heartbeat.py`
- Move: `bot/gateway/api.py` → `bot/channel/api.py`
- Move: `bot/gateway/status.py` → `bot/channel/status.py`
- Move: `bot/gateway/voice.py` → `bot/channel/voice.py`
- Update all imports across codebase

iMessage adapter: refactor to ChannelAdapter pattern (same as feishu/sms — replace `llm.reply()` with `gateway.handle()`).

Heartbeat, API, voice: move files, update imports. Full adapter refactor for these can be a follow-up.

- [ ] **Step 1: Move files with `git mv`**
- [ ] **Step 2: Update all imports**
- [ ] **Step 3: Run full test suite**
- [ ] **Step 4: Commit**

```bash
git commit -m "refactor: move gateway/ files to channel/"
```

---

### Task 6: Add `agent` field to channel configs

**Files:**
- Modify: `bot/config_schema.py`
- Modify: `config.yaml`

- [ ] **Step 1: Add `agent: str = ""` to `FeishuConfig`, `SMSConfig`, `IMessageConfig`**

```python
@dataclass
class FeishuConfig:
    enabled: bool = False
    agent: str = ""
    allow_from: list = field(default_factory=list)
```

- [ ] **Step 2: Update config.yaml**

```yaml
gateway:
  feishu:
    enabled: true
    agent: feishu
  sms:
    enabled: true
    agent: default
```

- [ ] **Step 3: Run tests, commit**

```bash
git commit -m "feat: add agent field to channel configs"
```

---

### Task 7: Wire up Gateway in main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Replace current adapter startup with Gateway**

```python
from bot.gateway import Gateway

gateway = Gateway()

# Register agents
for agent in agents:
    gateway.register_agent(agent.name, agent)

# Register feishu agent from workspace
if _gw_cfg.feishu.enabled:
    from bot.channel.feishu import FeishuAdapter
    adapter = FeishuAdapter()
    gateway.register_adapter(adapter)
    gateway.set_channel_agent("feishu", _gw_cfg.feishu.agent or "default")

# ... same for sms, imessage, etc.

tasks.append(gateway.start())
```

- [ ] **Step 2: Run full test suite**
- [ ] **Step 3: Commit**

```bash
git commit -m "feat: wire up Gateway exchange in main.py"
```

---

### Task 8: Cron delivery through Gateway

**Files:**
- Modify: `bot/services/cron.py`

- [ ] **Step 1: Replace delivery if/elif chain with gateway.deliver()**

```python
# OLD: 50 lines of if/elif for each channel
# NEW:
if reply.strip():
    from bot.gateway import get_gateway
    gw = get_gateway()
    if gw:
        await gw.deliver(job.delivery_channel, {"target_id": job.channel_id}, reply)
```

- [ ] **Step 2: Run tests, commit**

```bash
git commit -m "refactor: cron delivery through gateway exchange"
```

---

### Task 9: Update CLAUDE.md + cleanup

**Files:**
- Modify: `CLAUDE.md`
- Delete: `bot/gateway/` directory (should be empty after moves)

- [ ] **Step 1: Update project structure in CLAUDE.md**

Replace `bot/gateway/` section with `bot/channel/` and add `bot/gateway.py`.

- [ ] **Step 2: Remove empty `bot/gateway/` directory**
- [ ] **Step 3: Run full test suite**
- [ ] **Step 4: Commit**

```bash
git commit -m "docs: update CLAUDE.md for gateway exchange architecture"
```
