"""Twilio SMS inbound webhook — aiohttp server running in the same event loop."""

import asyncio
import base64
import hashlib
import hmac
from urllib.parse import urlencode

from aiohttp import web

from bot.config import get_config, get_secrets
from bot.utils.session_keys import sms_key
from bot.logger import get_logger
from bot.message import build_user_content

log = get_logger("sms")


# ── Twilio signature validation ─────────────────────────────────────────────

def validate_twilio_signature(
    url: str,
    params: dict[str, str],
    signature: str,
    auth_token: str,
) -> bool:
    """Validate Twilio request signature (HMAC-SHA1).

    https://www.twilio.com/docs/usage/security#validating-requests
    """
    # Build the data string: URL + sorted POST params concatenated
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]

    expected = base64.b64encode(
        hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
    ).decode()

    return hmac.compare_digest(expected, signature)


# ── Webhook handler ─────────────────────────────────────────────────────────

async def handle_incoming_sms(request: web.Request) -> web.Response:
    """Handle POST /sms from Twilio. Returns empty TwiML immediately,
    processes message in background to avoid Twilio's 15s timeout."""
    post = await request.post()
    params = {k: post[k] for k in post}

    # Validate signature if auth token is configured
    twilio_auth_token = get_secrets()["TWILIO_AUTH_TOKEN"]
    sms_webhook_url = get_config().gateway.sms.webhook_url
    if twilio_auth_token:
        sig = request.headers.get("X-Twilio-Signature", "")
        url = sms_webhook_url or str(request.url)
        if not validate_twilio_signature(url, params, sig, twilio_auth_token):
            log.warning("sms rejected: invalid Twilio signature")
            return web.Response(status=403, text="Invalid signature")

    from_number = params.get("From", "")
    body = params.get("Body", "").strip()
    num_media = int(params.get("NumMedia", "0"))

    log.info("sms ← from=%s len=%d media=%d", from_number, len(body), num_media)

    # Collect MMS image URLs
    image_urls: list[str] = []
    for i in range(num_media):
        media_url = params.get(f"MediaUrl{i}", "")
        media_type = params.get(f"MediaContentType{i}", "")
        if media_url and media_type.startswith("image/"):
            image_urls.append(media_url)

    # Return empty TwiML immediately so Twilio doesn't retry
    asyncio.create_task(_process_sms(from_number, body, image_urls))

    return web.Response(
        text='<?xml version="1.0" encoding="UTF-8"?><Response/>',
        content_type="application/xml",
    )


async def _process_sms(from_number: str, body: str, image_urls: list[str]) -> None:
    """Process an incoming SMS and reply via Twilio."""
    try:
        session_key = sms_key(from_number)
        user_content = build_user_content(body or "(empty message)", image_urls)

        from bot import llm
        reply_text = await llm.reply(session_key, user_content)

        if reply_text.strip():
            from bot.tools import run_sms
            result = await run_sms(to=from_number, message=reply_text)
            log.info("sms reply → %s: %s", from_number, result)
    except Exception:
        log.exception("sms processing failed for %s", from_number)


# ── Server lifecycle ────────────────────────────────────────────────────────

async def start_sms_server(port: int | None = None) -> None:
    """Start the aiohttp webhook server. Runs until cancelled."""
    port = port or get_config().gateway.sms.webhook_port

    app = web.Application()
    app.router.add_post("/sms", handle_incoming_sms)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("SMS webhook server listening on port %d", port)

    # Keep running until cancelled
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
