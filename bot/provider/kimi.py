"""Kimi Code (subscription) provider — Anthropic Messages API with API key auth.

Kimi (Moonshot AI, 月之暗面) ships two separate APIs:
  - Moonshot Open Platform  — OpenAI-compatible chat/completions, key MOONSHOT_API_KEY
  - Kimi Code / Kimi Coding — Anthropic Messages-compatible,     key KIMI_API_KEY

This provider targets the Kimi Code subscription endpoint. The wire format is
Anthropic Messages, so tool-use content blocks and SSE events pass straight
through to StreamProcessor with no conversion.
"""

import json
import os
from collections.abc import AsyncIterator

from bot.logger import get_logger
from bot.message import Message
from bot.provider.base import BaseProvider

log = get_logger("kimi")

ANTHROPIC_API_VERSION = "2023-06-01"
KIMI_USER_AGENT = "claude-code/0.1.0"


class KimiProvider(BaseProvider):
    ENV_KEY = "KIMI_API_KEY"

    def __init__(self, model: str):
        super().__init__()
        self.model = model
        from bot.config import get_config
        self.API_URL = get_config().llm.kimi.api_url

    def _get_api_key(self) -> str:
        key = os.environ.get(self.ENV_KEY, "")
        if not key:
            raise RuntimeError(f"{self.ENV_KEY} not set in environment")
        return key

    def _headers(self) -> dict:
        return {
            "x-api-key": self._get_api_key(),
            "anthropic-version": ANTHROPIC_API_VERSION,
            "User-Agent": KIMI_USER_AGENT,
            "Content-Type": "application/json",
            "accept": "application/json",
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
            "messages": messages,
            "stream": stream,
        }
        if system:
            body["system"] = system
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
        body = self._build_body(messages, system, tools, max_tokens, stream=True)
        client = self._get_client()
        headers = self._headers()

        log.info(
            "API request → %s | model=%s | messages=%d",
            self.API_URL, self.model, len(messages),
        )

        async with client.stream("POST", self.API_URL, json=body, headers=headers) as resp:
            if resp.status_code == 401:
                raise RuntimeError("Kimi API error (401): check KIMI_API_KEY")
            if resp.status_code != 200:
                text = await resp.aread()
                raise RuntimeError(f"Kimi API error ({resp.status_code}): {text.decode()}")

            event_type = None
            async for line in resp.aiter_lines():
                # SSE spec: "field:value" and "field: value" are both valid
                # (one optional leading space after colon). Kimi Code emits
                # the no-space form, real Anthropic emits the with-space form.
                if line.startswith("event:"):
                    event_type = line[6:].lstrip(" ")
                elif line.startswith("data:") and event_type:
                    data = json.loads(line[5:].lstrip(" "))
                    data["_event"] = event_type
                    if event_type == "message_start":
                        msg = data.get("message", {})
                        log.info(
                            "API response ← model=%s | id=%s",
                            msg.get("model"), msg.get("id"),
                        )
                    elif event_type == "message_delta":
                        usage = data.get("usage", {})
                        if usage:
                            log.info(
                                "API usage: input=%d output=%d",
                                usage.get("input_tokens", 0),
                                usage.get("output_tokens", 0),
                            )
                    yield data
                    event_type = None

    async def call(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        body = self._build_body(messages, system, tools, max_tokens, stream=False)
        client = self._get_client()
        headers = self._headers()

        resp = await client.post(self.API_URL, json=body, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Kimi API error ({resp.status_code}): {resp.text}")
        return resp.json()

    async def refresh_auth(self) -> None:
        """API key auth — nothing to refresh."""
        pass
