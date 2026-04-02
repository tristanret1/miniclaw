"""Twilio SMS channel adapter — aiohttp webhook server."""

import asyncio
import base64
import hashlib
import hmac

from aiohttp import web

from bot.channel import ChannelAdapter, InboundMessage
from bot.config import get_config, get_secrets
from bot.utils.session_keys import sms_key
from bot.logger import get_logger

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


# ── Adapter ──────────────────────────────────────────────────────────────────

class SMSAdapter(ChannelAdapter):
    """Twilio SMS channel adapter — aiohttp webhook inbound, Twilio API outbound."""

    name = "sms"
    supports_streaming = False

    def __init__(self) -> None:
        self._gateway = None
        self._runner: web.AppRunner | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self, gateway) -> None:
        """Start the aiohttp webhook server. Store gateway ref."""
        self._gateway = gateway

        port = get_config().gateway.sms.webhook_port

        app = web.Application()
        app.router.add_post("/sms", self._handle_incoming_sms)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()
        log.info("SMS webhook server listening on port %d", port)

    async def stop(self) -> None:
        """Cleanup aiohttp server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        log.info("SMS webhook server stopped")

    # ── Outbound ─────────────────────────────────────────────────────────────

    async def send(self, reply_ctx: dict, text: str) -> str:
        """Send SMS via Twilio. Supports target_id for cron/heartbeat delivery."""
        from bot.tools import run_sms
        phone = reply_ctx.get("phone_number") or reply_ctx.get("target_id")
        if not phone:
            return "Error: no phone_number or target_id in reply_ctx"
        return await run_sms(to=phone, message=text)

    # ── Inbound ───────────────────────────────────────────────────────────────

    async def _handle_incoming_sms(self, request: web.Request) -> web.Response:
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
        asyncio.create_task(self._process_sms(from_number, body, image_urls))

        return web.Response(
            text='<?xml version="1.0" encoding="UTF-8"?><Response/>',
            content_type="application/xml",
        )

    async def _process_sms(self, from_number: str, body: str, image_urls: list[str]) -> None:
        """Build InboundMessage and delegate to Gateway."""
        try:
            msg = InboundMessage(
                channel="sms",
                session_key=sms_key(from_number),
                text=body or "(empty message)",
                image_urls=image_urls,
                reply_ctx={"phone_number": from_number},
            )
            await self._gateway.handle(msg)
        except Exception:
            log.exception("sms processing failed for %s", from_number)

    # ── Standalone run (backward compat) ─────────────────────────────────────

    async def run(self) -> None:
        """Standalone run — starts the server and waits until cancelled."""
        from bot.gateway import Gateway
        gw = Gateway()
        await self.start(gw)
        try:
            await asyncio.Event().wait()
        finally:
            await self.stop()
