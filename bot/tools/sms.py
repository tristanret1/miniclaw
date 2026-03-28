"""sms and phone_call tools — Twilio-based messaging."""

import httpx

from bot.config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
)
from bot.constants import TWILIO_API_BASE
from bot.logger import get_logger

log = get_logger("tools")

SMS_TOOL = {
    "name": "sms",
    "description": (
        "Send an SMS text message via Twilio. "
        "Use this for notifications, reminders, or when the user asks to be texted."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient phone number in E.164 format (e.g. +14155551234).",
            },
            "message": {
                "type": "string",
                "description": "The text message to send (max 1600 characters).",
            },
        },
        "required": ["to", "message"],
    },
}

PHONE_CALL_TOOL = {
    "name": "phone_call",
    "description": (
        "Make a phone call using Twilio and speak a message via TTS (text-to-speech). "
        "Use this for urgent notifications, reminders, or when the user explicitly asks "
        "to be called. The message will be read aloud to the recipient."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient phone number in E.164 format (e.g. +14155551234).",
            },
            "message": {
                "type": "string",
                "description": "The text message to speak via TTS.",
            },
            "language": {
                "type": "string",
                "description": "TTS language/voice (default: zh-CN). Examples: en-US, ja-JP, fr-FR.",
            },
        },
        "required": ["to", "message"],
    },
}


async def run_sms(to: str, message: str) -> str:
    """Send an SMS via Twilio REST API."""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER]):
        return "Error: Twilio credentials not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER)"

    log.info("sms → to=%s len=%d", to, len(message))

    url = f"{TWILIO_API_BASE}/{TWILIO_ACCOUNT_SID}/Messages.json"
    payload = {
        "To": to,
        "From": TWILIO_FROM_NUMBER,
        "Body": message[:1600],
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                data=payload,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                timeout=30,
            )

        if resp.status_code == 201:
            data = resp.json()
            sid = data.get("sid", "unknown")
            log.info("sms ✓ sid=%s to=%s", sid, to)
            return f"SMS sent successfully (SID: {sid}) to {to}."
        else:
            error = resp.text[:500]
            log.error("sms ✗ status=%d: %s", resp.status_code, error)
            return f"Error: Twilio returned {resp.status_code} — {error}"
    except Exception as e:
        log.error("sms ✗ exception: %s", e)
        return f"Error sending SMS: {e}"


async def run_phone_call(to: str, message: str, language: str = "zh-CN") -> str:
    """Make a TTS phone call via Twilio REST API."""
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER]):
        return "Error: Twilio credentials not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER)"

    log.info("phone_call → to=%s lang=%s len=%d", to, language, len(message))

    # Build TwiML inline — Twilio accepts a URL or inline TwiML via the Twiml parameter
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say language="{language}">{message}</Say>'
        "</Response>"
    )

    url = f"{TWILIO_API_BASE}/{TWILIO_ACCOUNT_SID}/Calls.json"
    payload = {
        "To": to,
        "From": TWILIO_FROM_NUMBER,
        "Twiml": twiml,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                data=payload,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                timeout=30,
            )

        if resp.status_code == 201:
            data = resp.json()
            sid = data.get("sid", "unknown")
            log.info("phone_call ✓ call_sid=%s to=%s", sid, to)
            return f"Call initiated successfully (SID: {sid}). Message will be spoken to {to}."
        else:
            error = resp.text[:500]
            log.error("phone_call ✗ status=%d: %s", resp.status_code, error)
            return f"Error: Twilio returned {resp.status_code} — {error}"
    except Exception as e:
        log.error("phone_call ✗ exception: %s", e)
        return f"Error making call: {e}"
