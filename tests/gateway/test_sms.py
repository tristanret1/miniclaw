"""Tests for bot/sms_gateway.py — Twilio SMS webhook."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from bot.gateway.sms import handle_incoming_sms, validate_twilio_signature


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


# ── Webhook handler ─────────────────────────────────────────────────────────

@pytest.fixture
def sms_app():
    """Create an aiohttp app with the SMS webhook route."""
    app = web.Application()
    app.router.add_post("/sms", handle_incoming_sms)
    return app


@pytest.mark.asyncio
async def test_webhook_returns_empty_twiml(sms_app):
    """Webhook should return empty TwiML <Response/> immediately."""
    with patch("bot.gateway.sms.TWILIO_AUTH_TOKEN", ""):
        async with TestClient(TestServer(sms_app)) as client:
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
    with patch("bot.gateway.sms.TWILIO_AUTH_TOKEN", "real-token"), \
         patch("bot.gateway.sms.SMS_WEBHOOK_URL", "https://example.com/sms"):
        async with TestClient(TestServer(sms_app)) as client:
            resp = await client.post(
                "/sms",
                data={"From": "+14155551234", "Body": "Hello", "NumMedia": "0"},
                headers={"X-Twilio-Signature": "invalid"},
            )
            assert resp.status == 403


@pytest.mark.asyncio
async def test_webhook_calls_llm_reply(sms_app):
    """Webhook should call llm.reply and run_sms in background."""
    mock_reply = AsyncMock(return_value="Bot reply")
    mock_sms = AsyncMock(return_value="SMS sent")

    with patch("bot.gateway.sms.TWILIO_AUTH_TOKEN", ""), \
         patch("bot.gateway.sms.llm", create=True) as mock_llm_mod, \
         patch("bot.gateway.sms.run_sms", create=True, new=mock_sms):

        # Patch the lazy imports inside _process_sms
        with patch("bot.llm.reply", mock_reply), \
             patch("bot.tools.run_sms", mock_sms):

            async with TestClient(TestServer(sms_app)) as client:
                resp = await client.post("/sms", data={
                    "From": "+14155551234",
                    "Body": "Hello bot",
                    "NumMedia": "0",
                })
                assert resp.status == 200

            # Wait for background task
            await asyncio.sleep(0.3)

            mock_reply.assert_called_once()
            call_args = mock_reply.call_args
            assert call_args[0][0] == "sms:+14155551234"


@pytest.mark.asyncio
async def test_webhook_extracts_mms_images(sms_app):
    """Webhook should extract MMS image URLs."""
    mock_reply = AsyncMock(return_value="Got your image")
    mock_sms = AsyncMock(return_value="SMS sent")

    with patch("bot.gateway.sms.TWILIO_AUTH_TOKEN", ""), \
         patch("bot.llm.reply", mock_reply), \
         patch("bot.tools.run_sms", mock_sms):

        async with TestClient(TestServer(sms_app)) as client:
            resp = await client.post("/sms", data={
                "From": "+14155551234",
                "Body": "Check this photo",
                "NumMedia": "1",
                "MediaUrl0": "https://api.twilio.com/image.jpg",
                "MediaContentType0": "image/jpeg",
            })
            assert resp.status == 200

        await asyncio.sleep(0.3)

        mock_reply.assert_called_once()
        # The user_content should include the image
        call_args = mock_reply.call_args
        user_content = call_args[0][1]
        # With images, build_user_content returns a list
        assert isinstance(user_content, list)
