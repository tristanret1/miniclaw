"""Tests for bot/channel/sms.py — Twilio SMS channel adapter."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.channel.sms import SMSAdapter, validate_twilio_signature


# ── Signature validation ────────────────────────────────────────────────────

class TestValidateTwilioSignature:
    """Test HMAC-SHA1 signature validation using Twilio's documented example."""

    def test_valid_signature(self):
        # Twilio official test vector
        # https://www.twilio.com/docs/usage/security#validating-requests
        url = "https://mycompany.com/myapp.php?foo=1&bar=2"
        params = {
            "CallSid": "CA1234567890ABCDE",
            "Caller": "+14158675310",
            "Digits": "1234",
            "From": "+14158675310",
            "To": "+18005551212",
        }
        auth_token = "12345"

        # Compute expected signature manually for this test
        import base64
        import hashlib
        import hmac

        data = url
        for key in sorted(params.keys()):
            data += key + params[key]
        expected_sig = base64.b64encode(
            hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
        ).decode()

        assert validate_twilio_signature(url, params, expected_sig, auth_token) is True

    def test_invalid_signature(self):
        assert validate_twilio_signature(
            "https://example.com/sms",
            {"From": "+1234", "Body": "hi"},
            "bad-signature",
            "my-token",
        ) is False

    def test_empty_params(self):
        import base64
        import hashlib
        import hmac

        url = "https://example.com/sms"
        auth_token = "token123"
        expected = base64.b64encode(
            hmac.new(auth_token.encode(), url.encode(), hashlib.sha1).digest()
        ).decode()

        assert validate_twilio_signature(url, {}, expected, auth_token) is True


# ── Adapter fixture ──────────────────────────────────────────────────────────

@pytest.fixture
def sms_adapter():
    """Create an SMSAdapter with a fake gateway."""
    adapter = SMSAdapter()
    mock_gateway = MagicMock()
    mock_gateway.handle = AsyncMock()
    adapter._gateway = mock_gateway
    return adapter


@pytest.fixture
def sms_app(sms_adapter):
    """Create an aiohttp app with the SMS webhook route."""
    app = web.Application()
    app.router.add_post("/sms", sms_adapter._handle_incoming_sms)
    return app, sms_adapter


# ── Webhook handler ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webhook_returns_empty_twiml(sms_app):
    """Webhook should return empty TwiML <Response/> immediately."""
    app, adapter = sms_app
    with patch("bot.channel.sms.get_secrets", return_value={"TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "TWILIO_ACCOUNT_SID": ""}):
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/sms", data={
                "From": "+14155551234",
                "Body": "Hello bot",
                "NumMedia": "0",
            })
            assert resp.status == 200
            text = await resp.text()
            assert "<Response/>" in text
            assert resp.content_type == "application/xml"

    # Let background task settle
    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(sms_app):
    """Webhook should return 403 when signature validation fails."""
    app, adapter = sms_app
    mock_secrets = {"TWILIO_AUTH_TOKEN": "real-token", "TWILIO_FROM_NUMBER": "", "TWILIO_ACCOUNT_SID": ""}
    with patch("bot.channel.sms.get_secrets", return_value=mock_secrets), \
         patch("bot.channel.sms.get_config") as mock_cfg:
        mock_cfg.return_value.gateway.sms.webhook_url = "https://example.com/sms"
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/sms",
                data={"From": "+14155551234", "Body": "Hello", "NumMedia": "0"},
                headers={"X-Twilio-Signature": "invalid"},
            )
            assert resp.status == 403


@pytest.mark.asyncio
async def test_webhook_calls_gateway_handle(sms_app):
    """Webhook should call gateway.handle with InboundMessage in background."""
    app, adapter = sms_app

    mock_secrets = {"TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "TWILIO_ACCOUNT_SID": ""}
    with patch("bot.channel.sms.get_secrets", return_value=mock_secrets):
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/sms", data={
                "From": "+14155551234",
                "Body": "Hello bot",
                "NumMedia": "0",
            })
            assert resp.status == 200

        # Wait for background task
        await asyncio.sleep(0.3)

        adapter._gateway.handle.assert_called_once()
        call_args = adapter._gateway.handle.call_args
        inbound_msg = call_args[0][0]
        assert inbound_msg.channel == "sms"
        assert inbound_msg.session_key == "sms:+14155551234"
        assert inbound_msg.text == "Hello bot"
        assert inbound_msg.reply_ctx == {"phone_number": "+14155551234"}


@pytest.mark.asyncio
async def test_webhook_extracts_mms_images(sms_app):
    """Webhook should extract MMS image URLs and pass them in InboundMessage."""
    app, adapter = sms_app

    mock_secrets = {"TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "TWILIO_ACCOUNT_SID": ""}
    with patch("bot.channel.sms.get_secrets", return_value=mock_secrets):
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/sms", data={
                "From": "+14155551234",
                "Body": "Check this photo",
                "NumMedia": "1",
                "MediaUrl0": "https://api.twilio.com/image.jpg",
                "MediaContentType0": "image/jpeg",
            })
            assert resp.status == 200

        await asyncio.sleep(0.3)

        adapter._gateway.handle.assert_called_once()
        inbound_msg = adapter._gateway.handle.call_args[0][0]
        assert inbound_msg.image_urls == ["https://api.twilio.com/image.jpg"]


@pytest.mark.asyncio
async def test_webhook_empty_body_uses_placeholder(sms_app):
    """Empty SMS body should become '(empty message)' in InboundMessage.text."""
    app, adapter = sms_app

    mock_secrets = {"TWILIO_AUTH_TOKEN": "", "TWILIO_FROM_NUMBER": "", "TWILIO_ACCOUNT_SID": ""}
    with patch("bot.channel.sms.get_secrets", return_value=mock_secrets):
        async with TestClient(TestServer(app)) as client:
            await client.post("/sms", data={
                "From": "+14155551234",
                "Body": "",
                "NumMedia": "0",
            })

        await asyncio.sleep(0.3)

        inbound_msg = adapter._gateway.handle.call_args[0][0]
        assert inbound_msg.text == "(empty message)"


# ── send() ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_calls_run_sms():
    """send() should delegate to run_sms with correct args."""
    adapter = SMSAdapter()
    mock_run_sms = AsyncMock(return_value="SMS sent")

    with patch("bot.tools.run_sms", mock_run_sms):
        result = await adapter.send({"phone_number": "+14155551234"}, "Hello!")

    mock_run_sms.assert_called_once_with(to="+14155551234", message="Hello!")
    assert result == "SMS sent"
