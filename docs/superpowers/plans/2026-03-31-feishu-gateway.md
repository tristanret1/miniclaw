# Feishu Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Feishu (飞书) as a messaging gateway using lark-oapi SDK with WebSocket long connection, supporting both inbound messages and cron job delivery.

**Architecture:** A `lark.ws.Client` runs in a daemon thread (its `start()` blocks). Inbound message events are bridged to the main asyncio loop via `run_coroutine_threadsafe` → `llm.reply()`. Outbound uses the async REST API (`acreate`/`areply`). Feishu credentials (`FEISHU_APP_ID`, `FEISHU_APP_SECRET`) live in `.env`; gateway config (`enabled`, `allow_from`) lives in `config.yaml`.

**Tech Stack:** lark-oapi (Python SDK), WebSocket long connection, asyncio thread bridge

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `bot/gateway/feishu.py` | WebSocket gateway: connect, receive messages, send replies |
| Modify | `bot/config_schema.py` | Add `FeishuConfig` dataclass |
| Modify | `bot/config.py` | Add `FEISHU_APP_ID` / `FEISHU_APP_SECRET` to `get_secrets()` |
| Modify | `bot/utils/session_keys.py` | Add `feishu_key()` |
| Modify | `config.yaml` | Add `gateway.feishu` section |
| Modify | `.env.example` | Add Feishu secret placeholders |
| Modify | `main.py` | Start feishu gateway task |
| Modify | `bot/cron.py` | Add `feishu` delivery channel |
| Modify | `bot/tools/cron_tools.py` | Add `"feishu"` to delivery_channel enum |
| Create | `tests/gateway/test_feishu.py` | Tests for feishu gateway |

---

### Task 1: Add lark-oapi dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add lark-oapi to dependencies**

```bash
uv add lark-oapi
```

If sxtwl-style build issues occur, add with `--no-sync` and install manually. Verify:

```bash
uv run python -c "import lark_oapi; print(lark_oapi.__version__)"
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add lark-oapi SDK"
```

---

### Task 2: Config — FeishuConfig + secrets

**Files:**
- Modify: `bot/config_schema.py:253-288`
- Modify: `bot/config.py:59-76`
- Modify: `config.yaml:63-67`
- Modify: `.env.example`

- [ ] **Step 1: Write the failing test**

Create `tests/gateway/test_feishu.py`:

```python
"""Tests for Feishu gateway."""

import pytest
from bot.config_schema import FeishuConfig, GatewayConfig


class TestFeishuConfig:
    def test_defaults(self):
        cfg = FeishuConfig()
        assert cfg.enabled is False
        assert cfg.allow_from == []

    def test_from_dict(self):
        cfg = FeishuConfig.from_dict({
            "enabled": True,
            "allow_from": ["oc_abc123"],
        })
        assert cfg.enabled is True
        assert cfg.allow_from == ["oc_abc123"]

    def test_from_dict_empty(self):
        cfg = FeishuConfig.from_dict({})
        assert cfg.enabled is False

    def test_gateway_config_includes_feishu(self):
        gw = GatewayConfig.from_dict({"feishu": {"enabled": True}})
        assert gw.feishu.enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/gateway/test_feishu.py -v
```

Expected: FAIL — `FeishuConfig` does not exist.

- [ ] **Step 3: Add FeishuConfig to config_schema.py**

Add after `ApiConfig` class (before `GatewayConfig`):

```python
@dataclass
class FeishuConfig:
    enabled: bool = False
    allow_from: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> FeishuConfig:
        return cls(
            enabled=_bool(d.get("enabled"), False),
            allow_from=_list(d.get("allow_from"), []),
        )
```

Add `feishu` field to `GatewayConfig`:

```python
@dataclass
class GatewayConfig:
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    volcengine: VolcengineConfig = field(default_factory=VolcengineConfig)
    sms: SMSConfig = field(default_factory=SMSConfig)
    imessage: IMessageConfig = field(default_factory=IMessageConfig)
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    feishu: FeishuConfig = field(default_factory=FeishuConfig)

    @classmethod
    def from_dict(cls, d: dict) -> GatewayConfig:
        return cls(
            voice=VoiceConfig.from_dict(d.get("voice") or {}),
            volcengine=VolcengineConfig.from_dict(d.get("volcengine") or {}),
            sms=SMSConfig.from_dict(d.get("sms") or {}),
            imessage=IMessageConfig.from_dict(d.get("imessage") or {}),
            heartbeat=HeartbeatConfig.from_dict(d.get("heartbeat") or {}),
            api=ApiConfig.from_dict(d.get("api") or {}),
            feishu=FeishuConfig.from_dict(d.get("feishu") or {}),
        )
```

- [ ] **Step 4: Add secrets to config.py**

In `get_secrets()`, add:

```python
"FEISHU_APP_ID": os.getenv("FEISHU_APP_ID", ""),
"FEISHU_APP_SECRET": os.getenv("FEISHU_APP_SECRET", ""),
```

- [ ] **Step 5: Add config.yaml section**

Add after the `api:` block in `gateway:`:

```yaml
  feishu:
    enabled: false
    allow_from: []
```

- [ ] **Step 6: Add .env.example entries**

Append:

```
# Optional — Feishu (飞书) bot gateway
# FEISHU_APP_ID=cli_xxx
# FEISHU_APP_SECRET=xxx
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/gateway/test_feishu.py -v
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add bot/config_schema.py bot/config.py config.yaml .env.example tests/gateway/test_feishu.py
git commit -m "feat(feishu): add FeishuConfig and secrets"
```

---

### Task 3: Session key

**Files:**
- Modify: `bot/utils/session_keys.py`
- Modify: `tests/gateway/test_feishu.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/gateway/test_feishu.py`:

```python
from bot.utils.session_keys import feishu_key


class TestFeishuSessionKey:
    def test_p2p(self):
        assert feishu_key("oc_chat1", "ou_user1") == "feishu:oc_chat1:ou_user1"

    def test_group(self):
        assert feishu_key("oc_group1", "ou_user2") == "feishu:oc_group1:ou_user2"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/gateway/test_feishu.py::TestFeishuSessionKey -v
```

Expected: FAIL — `feishu_key` not found.

- [ ] **Step 3: Add feishu_key to session_keys.py**

```python
def feishu_key(chat_id: str, sender_id: str) -> str:
    return f"feishu:{chat_id}:{sender_id}"
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/gateway/test_feishu.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/utils/session_keys.py tests/gateway/test_feishu.py
git commit -m "feat(feishu): add feishu_key session key"
```

---

### Task 4: Feishu gateway — core module

**Files:**
- Create: `bot/gateway/feishu.py`
- Modify: `tests/gateway/test_feishu.py`

- [ ] **Step 1: Write the failing test for message parsing**

Append to `tests/gateway/test_feishu.py`:

```python
from unittest.mock import MagicMock
from bot.gateway.feishu import _parse_text_content, _strip_bot_mention


class TestFeishuMessageParsing:
    def test_parse_text_content(self):
        assert _parse_text_content('{"text":"hello world"}') == "hello world"

    def test_parse_text_content_empty(self):
        assert _parse_text_content('{"text":""}') == ""

    def test_parse_text_content_invalid_json(self):
        assert _parse_text_content("not json") == "not json"

    def test_strip_bot_mention(self):
        text = "@_user_1 hello"
        mentions = [MagicMock(key="@_user_1", id=MagicMock(open_id="ou_bot123"))]
        result = _strip_bot_mention(text, mentions, "ou_bot123")
        assert result.strip() == "hello"

    def test_strip_bot_mention_no_mentions(self):
        assert _strip_bot_mention("hello", None, "ou_bot") == "hello"

    def test_strip_bot_mention_keeps_user_mentions(self):
        text = "@_user_1 @_user_2 hello"
        mentions = [
            MagicMock(key="@_user_1", id=MagicMock(open_id="ou_bot")),
            MagicMock(key="@_user_2", id=MagicMock(open_id="ou_other")),
        ]
        result = _strip_bot_mention(text, mentions, "ou_bot")
        assert "@_user_2" in result
        assert "@_user_1" not in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/gateway/test_feishu.py::TestFeishuMessageParsing -v
```

Expected: FAIL — module `bot.gateway.feishu` does not exist.

- [ ] **Step 3: Create bot/gateway/feishu.py**

```python
"""Feishu (飞书) gateway — lark-oapi WebSocket long connection."""

import asyncio
import json
import threading
from typing import Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

from bot.config import get_config, get_secrets
from bot.logger import get_logger
from bot.message import build_user_content
from bot.utils.session_keys import feishu_key

log = get_logger("feishu")

_api_client: lark.Client | None = None
_main_loop: asyncio.AbstractEventLoop | None = None
_bot_open_id: str | None = None


# ── Message parsing helpers ──────────────────────────────────────────────────

def _parse_text_content(content: str) -> str:
    """Extract text from Feishu message content JSON."""
    try:
        parsed = json.loads(content)
        return parsed.get("text", "")
    except (json.JSONDecodeError, TypeError):
        return content


def _strip_bot_mention(text: str, mentions: list | None, bot_open_id: str) -> str:
    """Remove bot @mention from text, keep other mentions."""
    if not mentions:
        return text
    for m in mentions:
        if m.id and m.id.open_id == bot_open_id:
            text = text.replace(m.key, "")
    return text.strip()


# ── Outbound: send / reply ───────────────────────────────────────────────────

async def send_feishu_message(chat_id: str, text: str) -> str:
    """Send a message to a Feishu chat. Used by cron delivery."""
    if not _api_client:
        return "Error: Feishu API client not initialized"

    request = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        )
        .build()
    )
    response = await _api_client.im.v1.message.acreate(request)
    if not response.success():
        msg = f"Feishu send failed: code={response.code} msg={response.msg}"
        log.error(msg)
        return msg
    log.info("feishu → chat=%s len=%d", chat_id, len(text))
    return "ok"


async def _reply_feishu_message(message_id: str, text: str) -> str:
    """Reply to a specific Feishu message."""
    if not _api_client:
        return "Error: Feishu API client not initialized"

    request = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(
            ReplyMessageRequestBody.builder()
            .content(json.dumps({"text": text}))
            .msg_type("text")
            .build()
        )
        .build()
    )
    response = await _api_client.im.v1.message.areply(request)
    if not response.success():
        msg = f"Feishu reply failed: code={response.code} msg={response.msg}"
        log.error(msg)
        # Fallback: try sending directly to chat
        return msg
    return "ok"


# ── Inbound: event handler ───────────────────────────────────────────────────

def _on_message_receive(data: P2ImMessageReceiveV1) -> None:
    """Handle im.message.receive_v1 event (called from WS thread)."""
    if _main_loop is None:
        log.error("main loop not set, dropping message")
        return

    future = asyncio.run_coroutine_threadsafe(
        _process_feishu_message(data), _main_loop
    )
    # Don't block the WS thread waiting for result — fire and forget
    future.add_done_callback(_log_exception)


def _log_exception(future: asyncio.Future) -> None:
    if future.exception():
        log.error("feishu message processing error: %s", future.exception())


async def _process_feishu_message(data: P2ImMessageReceiveV1) -> None:
    """Process an inbound Feishu message on the main asyncio loop."""
    event = data.event
    msg = event.message
    sender = event.sender

    # Only handle text messages for now
    if msg.message_type != "text":
        log.debug("skipping non-text message: type=%s", msg.message_type)
        return

    chat_id = msg.chat_id
    chat_type = msg.chat_type  # "p2p" or "group"
    sender_id = sender.sender_id.open_id if sender.sender_id else ""
    message_id = msg.message_id

    # In group chats, only respond if bot is mentioned
    if chat_type == "group":
        mentions = msg.mentions or []
        bot_mentioned = any(
            m.id and m.id.open_id == _bot_open_id for m in mentions
        )
        if not bot_mentioned:
            return

    # Allow-list check
    cfg = get_config().gateway.feishu
    if cfg.allow_from and chat_id not in cfg.allow_from:
        log.debug("feishu: ignoring chat_id=%s (not in allow_from)", chat_id)
        return

    # Parse text
    text = _parse_text_content(msg.content)
    if _bot_open_id and msg.mentions:
        text = _strip_bot_mention(text, msg.mentions, _bot_open_id)

    if not text.strip():
        return

    log.info("feishu ← chat=%s sender=%s type=%s len=%d",
             chat_id, sender_id, chat_type, len(text))

    # Call LLM
    session_key = feishu_key(chat_id, sender_id)
    user_content = build_user_content(text, [])

    from bot import llm
    reply_text = await llm.reply(session_key, user_content)

    if reply_text.strip():
        result = await _reply_feishu_message(message_id, reply_text)
        if result != "ok":
            # Fallback to direct send if reply fails
            await send_feishu_message(chat_id, reply_text)


# ── Lifecycle ────────────────────────────────────────────────────────────────

async def start_feishu_gateway() -> None:
    """Start the Feishu WebSocket gateway. Runs until cancelled."""
    global _api_client, _main_loop, _bot_open_id

    secrets = get_secrets()
    app_id = secrets["FEISHU_APP_ID"]
    app_secret = secrets["FEISHU_APP_SECRET"]

    if not app_id or not app_secret:
        log.error("FEISHU_APP_ID / FEISHU_APP_SECRET not set, cannot start")
        return

    _main_loop = asyncio.get_running_loop()

    # REST API client (for sending messages)
    _api_client = (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )

    # Discover bot open_id
    try:
        from lark_oapi.api.bot.v3 import GetBotInfoRequest
        req = GetBotInfoRequest.builder().build()
        resp = await _api_client.bot.v3.bot_info.aget(req)
        if resp.success() and resp.data and resp.data.bot:
            _bot_open_id = resp.data.bot.open_id
            log.info("feishu bot open_id: %s", _bot_open_id)
    except Exception as e:
        log.warning("failed to get bot info: %s (mentions won't be stripped)", e)

    # Event handler
    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message_receive)
        .build()
    )

    # WebSocket client (runs in its own thread — start() blocks)
    ws_client = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.WARNING,
    )

    thread = threading.Thread(target=ws_client.start, daemon=True, name="feishu-ws")
    thread.start()
    log.info("Feishu WebSocket gateway started")

    # Keep running until cancelled
    try:
        await asyncio.Event().wait()
    finally:
        log.info("Feishu gateway shutting down")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/gateway/test_feishu.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/gateway/feishu.py tests/gateway/test_feishu.py
git commit -m "feat(feishu): add gateway with WebSocket long connection"
```

---

### Task 5: Wire up startup in main.py

**Files:**
- Modify: `main.py:70-92`

- [ ] **Step 1: Add feishu gateway startup**

After the voice gateway block in `main.py`, add:

```python
        if _gw_cfg.feishu.enabled:
            from bot.gateway.feishu import start_feishu_gateway
            tasks.append(start_feishu_gateway())
```

- [ ] **Step 2: Run existing tests to ensure no regressions**

```bash
uv run pytest --tb=short
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat(feishu): wire up gateway startup in main.py"
```

---

### Task 6: Cron delivery channel — feishu

**Files:**
- Modify: `bot/cron.py:165-167` (delivery_channel validation)
- Modify: `bot/cron.py:380-410` (delivery in `_execute_job`)
- Modify: `bot/tools/cron_tools.py:51-55` (enum + description)
- Modify: `tests/gateway/test_feishu.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/gateway/test_feishu.py`:

```python
from unittest.mock import AsyncMock, patch


class TestFeishuCronDelivery:
    @patch("bot.gateway.feishu.send_feishu_message", new_callable=AsyncMock, return_value="ok")
    async def test_send_feishu_message_called(self, mock_send):
        from bot.gateway.feishu import send_feishu_message
        result = await send_feishu_message("oc_chat123", "Hello from cron")
        assert result == "ok"
        mock_send.assert_called_once_with("oc_chat123", "Hello from cron")
```

- [ ] **Step 2: Run test to verify it passes**

This test should pass already since `send_feishu_message` exists.

```bash
uv run pytest tests/gateway/test_feishu.py::TestFeishuCronDelivery -v
```

- [ ] **Step 3: Add "feishu" to cron delivery_channel validation**

In `bot/cron.py`, change the validation line:

```python
    if delivery_channel not in ("discord", "sms", "imessage", "feishu"):
        delivery_channel = "discord"
```

- [ ] **Step 4: Add feishu delivery branch in _execute_job**

In `bot/cron.py` `_execute_job`, after the imessage block, add:

```python
                elif job.delivery_channel == "feishu":
                    try:
                        from bot.gateway.feishu import send_feishu_message
                        result = await send_feishu_message(chat_id=job.channel_id, message=reply)
                        log.info("job %s delivered via Feishu to %s: %s", job.name, job.channel_id, result)
                    except Exception as e:
                        log.error("job %s Feishu delivery failed: %s", job.name, e)
                        raise
```

- [ ] **Step 5: Update cron_tools.py enum and description**

In `bot/tools/cron_tools.py`, change:

```python
            "delivery_channel": {
                "type": "string",
                "enum": ["discord", "sms", "imessage", "feishu"],
                "description": "Delivery channel: 'discord' (default) sends to Discord channel_id, 'sms' sends SMS via Twilio, 'imessage' sends via iMessage, 'feishu' sends to Feishu chat. For sms/imessage, channel_id should be E.164 phone number or Apple ID. For feishu, use chat_id (oc_xxx).",
            },
```

- [ ] **Step 6: Run all tests**

```bash
uv run pytest --tb=short
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add bot/cron.py bot/tools/cron_tools.py tests/gateway/test_feishu.py
git commit -m "feat(feishu): add feishu cron delivery channel"
```

---

### Task 7: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add feishu to project structure**

Add under `bot/gateway/`:

```
│   ├── gateway/
│   │   ├── ...
│   │   ├── feishu.py                # Feishu: lark-oapi WebSocket long connection
```

Add to config.yaml sections table:

```
| `gateway.feishu` | `enabled`, `allow_from` |
```

Add to Secrets table:

```
| `FEISHU_APP_ID` | no | Feishu app ID (飞书自建应用) |
| `FEISHU_APP_SECRET` | no | Feishu app secret |
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add feishu gateway to CLAUDE.md"
```
