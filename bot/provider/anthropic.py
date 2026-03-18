"""Anthropic provider — OAuth-based Claude API with streaming SSE."""

import json
from collections.abc import AsyncIterator

import httpx

from bot.logger import get_logger
from bot.message import Message
from bot.oauth import load_credentials, refresh_token
from bot.provider.base import BaseProvider

log = get_logger("anthropic")


class AnthropicProvider(BaseProvider):
    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str):
        self.model = model
        self._http: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(120, connect=10),
                http2=True,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._http

    def _get_access_token(self) -> str:
        creds = load_credentials()
        if not creds:
            raise RuntimeError("Not authenticated. Run: python setup.py")
        return creds["access_token"]

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
        }

    def _build_body(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None,
        max_tokens: int,
        stream: bool,
    ) -> dict:
        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "stream": stream,
        }
        if tools:
            body["tools"] = tools
        return body

    async def stream(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[dict]:
        """POST /v1/messages with stream=true, yield parsed SSE events."""
        token = self._get_access_token()
        body = self._build_body(messages, system, tools, max_tokens, stream=True)
        client = self._get_client()

        async with client.stream(
            "POST", self.API_URL, json=body, headers=self._headers(token)
        ) as resp:
            if resp.status_code == 401:
                raise RuntimeError("Auth expired during stream")
            if resp.status_code != 200:
                text = await resp.aread()
                raise RuntimeError(f"Claude API error ({resp.status_code}): {text.decode()}")

            event_type = None
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: ") and event_type:
                    data = json.loads(line[6:])
                    data["_event"] = event_type
                    yield data
                    event_type = None

    async def call(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """POST /v1/messages, return full response dict."""
        token = self._get_access_token()
        body = self._build_body(messages, system, tools, max_tokens, stream=False)
        client = self._get_client()

        resp = await client.post(self.API_URL, json=body, headers=self._headers(token))

        if resp.status_code == 401:
            creds = load_credentials()
            if creds and creds.get("refresh_token"):
                new_creds = refresh_token(creds)
                resp = await client.post(
                    self.API_URL, json=body, headers=self._headers(new_creds["access_token"])
                )

        if resp.status_code != 200:
            raise RuntimeError(f"Claude API error ({resp.status_code}): {resp.text}")

        return resp.json()

    async def refresh_auth(self) -> None:
        """Refresh OAuth access token."""
        creds = load_credentials()
        if creds and creds.get("refresh_token"):
            refresh_token(creds)
        else:
            raise RuntimeError("No refresh token available")
