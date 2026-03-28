"""Twilio API client for SMS and voice calls."""
import httpx

from bot.constants import TWILIO_API_BASE
from bot.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER


class TwilioClient:
    def __init__(self, account_sid="", auth_token="", from_number=""):
        self._sid = account_sid or TWILIO_ACCOUNT_SID
        self._token = auth_token or TWILIO_AUTH_TOKEN
        self._from = from_number or TWILIO_FROM_NUMBER

    def is_configured(self) -> bool:
        return bool(self._sid and self._token and self._from)

    async def send_sms(self, to: str, body: str) -> dict:
        if not self.is_configured():
            return {"error": "Twilio credentials not configured"}
        url = f"{TWILIO_API_BASE}/{self._sid}/Messages.json"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                auth=(self._sid, self._token),
                data={"To": to, "From": self._from, "Body": body},
            )
            return resp.json()

    async def make_call(self, to: str, twiml: str) -> dict:
        if not self.is_configured():
            return {"error": "Twilio credentials not configured"}
        url = f"{TWILIO_API_BASE}/{self._sid}/Calls.json"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                auth=(self._sid, self._token),
                data={"To": to, "From": self._from, "Twiml": twiml},
            )
            return resp.json()
