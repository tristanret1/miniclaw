"""Feishu (飞书) channel adapter — lark-oapi WebSocket long connection."""

import asyncio
import json
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import lark_oapi as lark

from bot.channel import ChannelAdapter, InboundMessage
from bot.config import get_config, get_secrets
from bot.logger import get_logger
from bot.utils.session_keys import feishu_key

log = get_logger("feishu")

_MSG_ID_MAX = 500


# ── Message parsing helpers (pure, module-level) ─────────────────────────────

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


# ── Adapter ───────────────────────────────────────────────────────────────────

class FeishuAdapter(ChannelAdapter):
    """Feishu transport adapter — WebSocket inbound, REST API outbound."""

    name = "feishu"
    supports_streaming = False

    def __init__(self) -> None:
        self._gateway = None
        self._api_client = None
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._bot_open_id: str | None = None
        self._processed_msg_ids: set[str] = set()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self, gateway) -> None:
        """Start the Feishu WebSocket gateway. Stores gateway ref."""
        self._gateway = gateway

        secrets = get_secrets()
        app_id = secrets.get("FEISHU_APP_ID", "")
        app_secret = secrets.get("FEISHU_APP_SECRET", "")

        if not app_id or not app_secret:
            log.error("FEISHU_APP_ID / FEISHU_APP_SECRET not set, cannot start")
            return

        import lark_oapi as lark

        self._main_loop = asyncio.get_running_loop()

        # REST API client (for sending messages)
        self._api_client = (
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
                .token_types({lark.AccessTokenType.TENANT}) \
                .build()
            resp = await self._api_client.arequest(req)
            raw_body = resp.raw.content if resp.raw else b""
            body = json.loads(raw_body) if raw_body else {}
            if body.get("code", -1) == 0:
                bot_info = body.get("bot", {})
                self._bot_open_id = bot_info.get("open_id")
                log.info("feishu bot: %s (open_id=%s)", bot_info.get("app_name"), self._bot_open_id)
            else:
                log.warning("failed to get bot info: %s", raw_body[:500])
        except Exception as e:
            log.warning("failed to get bot info: %s", e)

        # Closure captures self for the WS thread callback
        def on_msg(data: object) -> None:
            if self._main_loop:
                future = asyncio.run_coroutine_threadsafe(
                    self._process_message(data), self._main_loop
                )
                future.add_done_callback(self._log_exception)

        def _noop(data: object) -> None:
            pass

        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_msg)
            .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(_noop)
            .build()
        )

        # WebSocket client runs in its own thread
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

    async def stop(self) -> None:
        """Graceful shutdown (WS thread is daemon, will exit with process)."""
        log.info("Feishu gateway shutting down")

    # ── Outbound ─────────────────────────────────────────────────────────────

    async def send(self, reply_ctx: dict, text: str) -> str:
        """Send reply. Tries message reply first, falls back to chat send.

        Supports reply_ctx["target_id"] for cron/heartbeat delivery.
        """
        message_id = reply_ctx.get("message_id")
        chat_id = reply_ctx.get("chat_id") or reply_ctx.get("target_id")
        if message_id:
            result = await self._reply(message_id, text)
            if result == "ok":
                return result
        if chat_id:
            return await self._send(chat_id, text)
        return "Error: no chat_id, target_id, or message_id in reply_ctx"

    async def _send(self, chat_id: str, message: str) -> str:
        """Send a message to a Feishu chat."""
        if not self._api_client:
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
        response = await self._api_client.im.v1.message.acreate(request)
        if not response.success():
            msg = f"Feishu send failed: code={response.code} msg={response.msg}"
            log.error(msg)
            return msg
        log.info("feishu → chat=%s len=%d", chat_id, len(message))
        return "ok"

    async def _reply(self, message_id: str, text: str) -> str:
        """Reply to a specific Feishu message."""
        if not self._api_client:
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
        response = await self._api_client.im.v1.message.areply(request)
        if not response.success():
            msg = f"Feishu reply failed: code={response.code} msg={response.msg}"
            log.error(msg)
            return msg
        return "ok"

    # ── Inbound ───────────────────────────────────────────────────────────────

    @staticmethod
    def _log_exception(future: asyncio.Future) -> None:
        if future.exception():
            log.error("feishu message processing error: %s", future.exception())

    async def _process_message(self, data: object) -> None:
        """Process an inbound Feishu message on the main asyncio loop."""
        event = data.event
        msg = event.message
        sender = event.sender

        # Dedup: skip if already processed (Feishu may re-push on timeout)
        msg_id = msg.message_id
        if msg_id in self._processed_msg_ids:
            log.debug("feishu: skipping duplicate message_id=%s", msg_id)
            return
        self._processed_msg_ids.add(msg_id)
        if len(self._processed_msg_ids) > _MSG_ID_MAX:
            to_remove = len(self._processed_msg_ids) - _MSG_ID_MAX
            for _ in range(to_remove):
                self._processed_msg_ids.pop()

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
                m.id and m.id.open_id == self._bot_open_id for m in mentions
            ) if self._bot_open_id else bool(mentions)
            if not bot_mentioned:
                return

        # Allow-list check
        cfg = get_config().gateway.feishu
        if cfg.allow_from and chat_id not in cfg.allow_from:
            log.debug("feishu: ignoring chat_id=%s (not in allow_from)", chat_id)
            return

        # Parse text
        text = _parse_text_content(msg.content)
        if self._bot_open_id and msg.mentions:
            text = _strip_bot_mention(text, msg.mentions, self._bot_open_id)

        if not text.strip():
            return

        log.info("feishu ← chat=%s sender=%s type=%s len=%d",
                 chat_id, sender_id, chat_type, len(text))

        # Build InboundMessage and delegate to Gateway
        inbound = InboundMessage(
            channel="feishu",
            session_key=feishu_key(chat_id, sender_id),
            text=text,
            reply_ctx={"chat_id": chat_id, "message_id": message_id},
        )
        await self._gateway.handle(inbound)

    # ── Standalone run (backward compat until Task 7) ─────────────────────────

    async def run(self) -> None:
        """Standalone run — used before Gateway is wired in main.py."""
        from bot.gateway import Gateway
        gw = Gateway()
        await self.start(gw)
        try:
            await asyncio.Event().wait()
        finally:
            await self.stop()


# ── Module-level helper for cron delivery (backward compat) ──────────────────

async def send_feishu_message(chat_id: str, message: str) -> str:
    """Send a message to a Feishu chat. Used by cron delivery.

    This is a convenience wrapper that creates a temporary adapter instance.
    Task 8 will replace cron delivery with Gateway.deliver() instead.
    """
    adapter = FeishuAdapter()
    secrets = get_secrets()
    app_id = secrets.get("FEISHU_APP_ID", "")
    app_secret = secrets.get("FEISHU_APP_SECRET", "")

    if not app_id or not app_secret:
        return "Error: Feishu API client not initialized"

    import lark_oapi as lark
    adapter._api_client = (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )
    return await adapter._send(chat_id, message)
