"""Feishu (飞书) gateway — lark-oapi WebSocket long connection."""

import asyncio
import json
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import lark_oapi as lark

from bot.config import get_config, get_secrets
from bot.logger import get_logger
from bot.message import build_user_content
from bot.utils.session_keys import feishu_key

log = get_logger("feishu")

_api_client: "lark.Client | None" = None
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

async def send_feishu_message(chat_id: str, message: str) -> str:
    """Send a message to a Feishu chat. Used by cron delivery."""
    if not _api_client:
        return "Error: Feishu API client not initialized"

    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
    request = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": message}))
            .build()
        )
        .build()
    )
    response = await _api_client.im.v1.message.acreate(request)
    if not response.success():
        msg = f"Feishu send failed: code={response.code} msg={response.msg}"
        log.error(msg)
        return msg
    log.info("feishu → chat=%s len=%d", chat_id, len(message))
    return "ok"


async def _reply_feishu_message(message_id: str, text: str) -> str:
    """Reply to a specific Feishu message."""
    if not _api_client:
        return "Error: Feishu API client not initialized"

    from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
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
        return msg
    return "ok"


# ── Inbound: event handler ───────────────────────────────────────────────────

def _on_message_receive(data: object) -> None:
    """Handle im.message.receive_v1 event (called from WS thread)."""
    if _main_loop is None:
        log.error("main loop not set, dropping message")
        return

    future = asyncio.run_coroutine_threadsafe(
        _process_feishu_message(data), _main_loop
    )
    future.add_done_callback(_log_exception)


def _log_exception(future: asyncio.Future) -> None:
    if future.exception():
        log.error("feishu message processing error: %s", future.exception())


async def _process_feishu_message(data: object) -> None:
    """Process an inbound Feishu message on the main asyncio loop."""
    event = data.event
    msg = event.message
    sender = event.sender

    # Only handle text messages for now
    if msg.message_type != "text":
        log.debug("skipping non-text message: type=%s", msg.message_type)
        return

    chat_id = msg.chat_id
    chat_type = msg.chat_type
    sender_id = sender.sender_id.open_id if sender.sender_id else ""
    message_id = msg.message_id

    # In group chats, only respond if bot is mentioned
    if chat_type == "group":
        mentions = msg.mentions or []
        bot_mentioned = any(
            m.id and m.id.open_id == _bot_open_id for m in mentions
        ) if _bot_open_id else bool(mentions)
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

    import lark_oapi as lark

    _main_loop = asyncio.get_running_loop()

    # REST API client (for sending messages)
    _api_client = (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )

    # Discover bot open_id via raw API call
    try:
        from lark_oapi.core.model.base_request import BaseRequest
        req = BaseRequest.builder() \
            .http_method(lark.HttpMethod.GET) \
            .uri("/open-apis/bot/v3/info") \
            .build()
        resp = await _api_client.arequest(req)
        raw_body = resp.raw.content if resp.raw else b""
        body = json.loads(raw_body) if raw_body else {}
        if body.get("code", -1) == 0:
            bot_info = body.get("bot", {})
            _bot_open_id = bot_info.get("open_id")
            log.info("feishu bot: %s (open_id=%s)", bot_info.get("app_name"), _bot_open_id)
        else:
            log.warning("failed to get bot info: %s", raw_body[:500])
    except Exception as e:
        log.warning("failed to get bot info: %s", e)

    # Event handler (register noop for events we don't care about to suppress SDK warnings)
    def _noop(data: object) -> None:
        pass

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message_receive)
        .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(_noop)
        .build()
    )

    # WebSocket client (runs in its own thread — start() blocks).
    # lark_oapi's ws.Client uses a module-level event loop; we must give the
    # worker thread a fresh loop so it doesn't collide with the main asyncio.run().
    def _run_ws() -> None:
        import lark_oapi.ws.client as _ws_mod
        _ws_mod.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_ws_mod.loop)

        ws_client = lark.ws.Client(
            app_id,
            app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.WARNING,
        )
        ws_client.start()

    thread = threading.Thread(target=_run_ws, daemon=True, name="feishu-ws")
    thread.start()
    log.info("Feishu WebSocket gateway started")

    # Keep running until cancelled
    try:
        await asyncio.Event().wait()
    finally:
        log.info("Feishu gateway shutting down")
