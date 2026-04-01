"""WhatsApp gateway — neonize (whatsmeow bindings) WebSocket long connection."""

import asyncio
from pathlib import Path

from bot.config import get_config, PROJECT_ROOT
from bot.logger import get_logger
from bot.message import build_user_content
from bot.utils.session_keys import whatsapp_key

log = get_logger("whatsapp")

_client = None  # neonize NewClient instance
_main_loop: asyncio.AbstractEventLoop | None = None

MAX_MESSAGE_LEN = 4096


# ── Helpers ─────────────────────────────────────────────────────────────────

def _jid_to_phone(jid) -> str:
    """Extract phone number from WhatsApp JID (e.g. '8613800138000@s.whatsapp.net')."""
    user = jid.User if hasattr(jid, "User") else str(jid)
    return user.split("@")[0] if "@" in str(user) else str(user)


def _chunk_message(text: str, limit: int = MAX_MESSAGE_LEN) -> list[str]:
    """Split text into chunks respecting the message length limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks


# ── Inbound: event handler ──────────────────────────────────────────────────

def _on_message(client, message) -> None:
    """Handle incoming WhatsApp message (called from neonize thread)."""
    if _main_loop is None:
        log.error("main loop not set, dropping message")
        return

    future = asyncio.run_coroutine_threadsafe(
        _process_message(client, message), _main_loop
    )
    future.add_done_callback(_log_exception)


def _log_exception(future: asyncio.Future) -> None:
    if future.exception():
        log.error("whatsapp message processing error: %s", future.exception())


async def _process_message(client, message) -> None:
    """Process an inbound WhatsApp message on the main asyncio loop."""
    from neonize.proto.Neonize_pb2 import Message as NeonizeMessage

    info = message.Info
    sender_jid = info.MessageSource.Sender
    chat_jid = info.MessageSource.Chat
    phone = _jid_to_phone(sender_jid)
    is_from_me = info.MessageSource.IsFromMe

    # Skip own messages
    if is_from_me:
        return

    # Allow-list check
    cfg = get_config().gateway.whatsapp
    if cfg.allow_from and phone not in cfg.allow_from:
        log.debug("whatsapp: ignoring phone=%s (not in allow_from)", phone)
        return

    # Extract content
    msg = message.Message
    text = ""
    image_data: bytes | None = None
    audio_data: bytes | None = None

    if msg.conversation:
        text = msg.conversation
    elif msg.extendedTextMessage and msg.extendedTextMessage.text:
        text = msg.extendedTextMessage.text
    elif msg.imageMessage:
        try:
            image_data = await asyncio.to_thread(client.download_any, message)
            text = msg.imageMessage.caption or ""
        except Exception as e:
            log.error("whatsapp: image download failed: %s", e)
            await _send_reply(client, chat_jid, "Sorry, I couldn't download that image.")
            return
    elif msg.audioMessage:
        try:
            audio_data = await asyncio.to_thread(client.download_any, message)
        except Exception as e:
            log.error("whatsapp: audio download failed: %s", e)
            await _send_reply(client, chat_jid, "Sorry, I couldn't download that audio.")
            return
    else:
        log.debug("whatsapp: skipping unsupported message type")
        return

    # Transcribe audio via STT
    if audio_data is not None:
        try:
            from bot.audio.stt import transcribe
            text = await transcribe(audio_data)
            if not text:
                return
        except Exception as e:
            log.error("whatsapp: STT failed: %s", e)
            await _send_reply(client, chat_jid, "Sorry, I couldn't transcribe that audio.")
            return

    if not text.strip() and image_data is None:
        return

    log.info("whatsapp ← phone=%s len=%d has_image=%s has_audio=%s",
             phone, len(text), image_data is not None, audio_data is not None)

    # Build user content
    if image_data is not None:
        import base64
        b64 = base64.standard_b64encode(image_data).decode()
        # Detect media type from imageMessage
        media_type = "image/jpeg"
        if msg.imageMessage and msg.imageMessage.mimetype:
            media_type = msg.imageMessage.mimetype
        user_content = []
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        })
        if text.strip():
            user_content.append({"type": "text", "text": text})
        else:
            user_content.append({"type": "text", "text": "What's in this image?"})
    else:
        user_content = build_user_content(text, [])

    # Call LLM
    session_key = whatsapp_key(phone)
    from bot import llm
    reply_text = await llm.reply(session_key, user_content)

    if reply_text.strip():
        await _send_reply(client, chat_jid, reply_text)


# ── Outbound ────────────────────────────────────────────────────────────────

async def _send_reply(client, chat_jid, text: str) -> None:
    """Send a text reply, chunking if needed."""
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message as WAMessage

    for chunk in _chunk_message(text):
        try:
            wa_msg = WAMessage(conversation=chunk)
            await asyncio.to_thread(client.send_message, chat_jid, wa_msg)
            log.info("whatsapp → phone=%s len=%d", _jid_to_phone(chat_jid), len(chunk))
        except Exception as e:
            log.error("whatsapp: send failed: %s", e)


# ── Lifecycle ───────────────────────────────────────────────────────────────

async def start_whatsapp_gateway() -> None:
    """Start the WhatsApp gateway via neonize. Runs until cancelled."""
    global _client, _main_loop

    cfg = get_config().gateway.whatsapp
    session_db = PROJECT_ROOT / cfg.session_db

    _main_loop = asyncio.get_running_loop()

    from neonize.client import NewClient
    from neonize.events import (
        ConnectedEv,
        DisconnectedEv,
        MessageEv,
        PairStatusEv,
        event,
    )

    _client = NewClient(str(session_db))

    @_client.event(ConnectedEv)
    def on_connected(_client_ref, _evt):
        log.info("WhatsApp connected")

    @_client.event(DisconnectedEv)
    def on_disconnected(_client_ref, _evt):
        log.warning("WhatsApp disconnected")

    @_client.event(PairStatusEv)
    def on_pair_status(_client_ref, evt):
        log.info("WhatsApp pair status: %s", evt)

    @_client.event(MessageEv)
    def on_message_event(_client_ref, evt):
        _on_message(_client_ref, evt)

    # neonize's connect() blocks — run in a thread
    def _run_client():
        _client.connect()

    thread_task = asyncio.get_running_loop().run_in_executor(None, _run_client)
    log.info("WhatsApp gateway started (session=%s)", session_db)

    try:
        await asyncio.Event().wait()
    finally:
        log.info("WhatsApp gateway shutting down")
        try:
            _client.disconnect()
        except Exception:
            pass
