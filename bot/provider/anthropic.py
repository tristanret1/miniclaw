"""Anthropic provider — OAuth-based Claude API with streaming SSE.

Aligns with pi-mono/packages/ai Anthropic provider conventions:
- Claude Code identity headers and system prompt prefix for OAuth tokens
- Prompt caching via cache_control on system and last user message
- Beta features: claude-code, oauth, interleaved-thinking
"""

import json
from collections.abc import AsyncIterator

from bot.constants import (
    ANTHROPIC_API_URL,
    ANTHROPIC_API_VERSION,
    ANTHROPIC_BETA_FEATURES,
    CLAUDE_CODE_SYSTEM_PREFIX,
    CLAUDE_CODE_VERSION,
)
from bot.logger import get_logger
from bot.message import Message
from bot.oauth.anthropic import load_credentials, refresh_token
from bot.provider.base import BaseProvider

log = get_logger("anthropic")


class AnthropicProvider(BaseProvider):
    API_URL = ANTHROPIC_API_URL

    def __init__(self, model: str):
        super().__init__()
        self.model = model

    def _get_access_token(self) -> str:
        creds = load_credentials()
        if not creds:
            raise RuntimeError("Not authenticated. Run: python setup.py")
        return creds["access_token"]

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "anthropic-version": ANTHROPIC_API_VERSION,
            "anthropic-beta": ANTHROPIC_BETA_FEATURES,
            "user-agent": f"claude-cli/{CLAUDE_CODE_VERSION}",
            "x-app": "cli",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

    @staticmethod
    def _build_system_blocks(system: str) -> list[dict]:
        """Build system prompt as array of text blocks with Claude Code prefix and cache control."""
        blocks = [
            {
                "type": "text",
                "text": CLAUDE_CODE_SYSTEM_PREFIX,
                "cache_control": {"type": "ephemeral"},
            },
        ]
        if system:
            blocks.append({
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            })
        return blocks

    @staticmethod
    def _inject_cache_breakpoints(messages: list[Message]) -> list[Message]:
        """在 messages 中注入 cache_control 断点，最大化 prompt cache 命中率。

        策略：在最后一个 user turn 之前的那个 user turn 上打断点。
        这样 system + 旧历史 都会被缓存，每轮只有最新的一轮对话需要计费。

        Claude 允许最多 4 个 cache 断点，我们用掉 2 个给 system，
        剩余放在 messages 中靠后的位置（倒数第二个 user turn 和 tools）。
        """
        if not messages:
            return messages

        # 找所有 user 消息的索引
        user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]

        if len(user_indices) < 2:
            # 只有一轮对话，没有旧历史可缓存
            return messages

        # 深拷贝要修改的消息，避免污染 session cache
        messages = list(messages)

        # 在倒数第二个 user turn 上打断点
        target_idx = user_indices[-2]
        msg = dict(messages[target_idx])
        content = msg.get("content")

        if isinstance(content, str):
            # 纯文本 → 转为 text block 加 cache_control
            msg["content"] = [{
                "type": "text",
                "text": content,
                "cache_control": {"type": "ephemeral"},
            }]
        elif isinstance(content, list):
            # 已经是 block 列表 → 在最后一个 block 上加 cache_control
            content = [dict(b) if isinstance(b, dict) else b for b in content]
            for i in range(len(content) - 1, -1, -1):
                if isinstance(content[i], dict):
                    content[i] = {**content[i], "cache_control": {"type": "ephemeral"}}
                    break
            msg["content"] = content

        messages[target_idx] = msg
        return messages

    def _build_body(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None,
        max_tokens: int,
        stream: bool,
    ) -> dict:
        # 注入 cache 断点：system 上已有，messages 中再加一个
        cached_messages = self._inject_cache_breakpoints(messages)

        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": self._build_system_blocks(system),
            "messages": cached_messages,
            "stream": stream,
        }
        if tools:
            # 在 tools 最后一个上也打 cache 断点（tools 定义不变，适合缓存）
            tools = list(tools)
            if tools:
                tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
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

        log.info("API request → %s | model=%s | messages=%d", self.API_URL, self.model, len(messages))

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
                    if event_type == "message_start":
                        msg = data.get("message", {})
                        log.info("API response ← model=%s | id=%s", msg.get("model"), msg.get("id"))
                    elif event_type == "message_delta":
                        usage = data.get("usage", {})
                        if usage:
                            log.info(
                                "API usage: input=%d output=%d cache_read=%d cache_create=%d",
                                usage.get("input_tokens", 0),
                                usage.get("output_tokens", 0),
                                usage.get("cache_read_input_tokens", 0),
                                usage.get("cache_creation_input_tokens", 0),
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
