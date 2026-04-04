"""Base provider for OpenAI-compatible APIs (GLM, MiniMax, etc.).

Handles the common wire format: OpenAI chat completions with SSE streaming,
function calling, and reasoning_content. Subclasses only need to set the
API URL, model, auth headers, and any request body tweaks.

Internally translates between the Anthropic message format used by
StreamProcessor and the OpenAI chat completions format.
"""

import json
import os
from collections.abc import AsyncIterator

from bot.logger import get_logger
from bot.message import Message
from bot.provider.base import BaseProvider

log = get_logger("openai_compat")


# ── Message format conversion ────────────────────────────────────────────────


def to_openai_messages(messages: list[Message], system: str) -> list[dict]:
    """Convert internal Anthropic-style messages to OpenAI chat format.

    Mapping:
      system prompt     → {role: "system", content: str}
      user text         → {role: "user", content: str}
      user image+text   → {role: "user", content: [{type: "text"}, {type: "image_url"}]}
      assistant text    → {role: "assistant", content: str}
      assistant tool_use→ {role: "assistant", tool_calls: [...]}
      user tool_result  → {role: "tool", tool_call_id: ..., content: str}
    """
    result: list[dict] = []

    if system:
        result.append({"role": "system", "content": system})

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role == "user":
            if isinstance(content, str):
                result.append({"role": "user", "content": content})
            elif isinstance(content, list):
                # Could be tool_result blocks or mixed content
                has_tool_results = any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in content
                )
                if has_tool_results:
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            output = block.get("content", "")
                            if isinstance(output, list):
                                output = json.dumps(output, ensure_ascii=False)
                            result.append({
                                "role": "tool",
                                "tool_call_id": block["tool_use_id"],
                                "content": str(output),
                            })
                else:
                    # Mixed text + image content
                    parts: list[dict] = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                parts.append({"type": "text", "text": block["text"]})
                            elif block.get("type") == "image":
                                source = block.get("source", {})
                                if source.get("type") == "url":
                                    parts.append({
                                        "type": "image_url",
                                        "image_url": {"url": source["url"]},
                                    })
                    if parts:
                        result.append({"role": "user", "content": parts})

        elif role == "assistant":
            if isinstance(content, str):
                result.append({"role": "assistant", "content": content})
            elif isinstance(content, list):
                text_parts = []
                tool_calls = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block["text"])
                        elif block.get("type") == "tool_use":
                            args = block.get("input", {})
                            tool_calls.append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(args, ensure_ascii=False)
                                    if isinstance(args, dict) else str(args),
                                },
                            })
                assistant_msg: dict = {"role": "assistant", "content": "\n".join(text_parts) or ""}
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                result.append(assistant_msg)

    return result


def to_openai_tools(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool definitions to OpenAI function format."""
    result: list[dict] = []
    for tool in tools:
        result.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return result


# ── Base provider ─────────────────────────────────────────────────────────────


class OpenAICompatProvider(BaseProvider):
    """Base class for providers using OpenAI-compatible chat completions API."""

    # Subclasses must set these
    API_URL: str = ""
    ENV_KEY: str = ""  # e.g. "GLM_API_KEY"

    def __init__(self, model: str):
        super().__init__()
        self.model = model

    def _get_api_key(self) -> str:
        key = os.environ.get(self.ENV_KEY, "")
        if not key:
            raise RuntimeError(f"{self.ENV_KEY} not set in environment")
        return key

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_api_key()}",
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
        """Build request body. Subclasses can override for provider quirks."""
        body: dict = {
            "model": self.model,
            "messages": to_openai_messages(messages, system),
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            body["tools"] = to_openai_tools(tools)
            body["tool_choice"] = "auto"
        return body

    async def stream(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[dict]:
        """Stream via OpenAI-compatible SSE, yield Anthropic-compatible events."""
        body = self._build_body(messages, system, tools, max_tokens, stream=True)
        client = self._get_client()
        headers = self._headers()

        log.info("API request → %s | model=%s | messages=%d", self.API_URL, self.model, len(messages))

        async with client.stream("POST", self.API_URL, json=body, headers=headers) as resp:
            if resp.status_code == 401:
                raise RuntimeError("Auth failed — check API key")
            if resp.status_code != 200:
                text = await resp.aread()
                raise RuntimeError(f"API error ({resp.status_code}): {text.decode()}")

            current_text_block = False
            tool_blocks: dict[int, dict] = {}  # index → {id, name, partial_args}
            stop_reason = "end_turn"

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break

                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                choices = event.get("choices", [])
                if not choices:
                    # Usage-only chunk
                    usage = event.get("usage")
                    if usage:
                        log.info(
                            "API usage: input=%d output=%d total=%d",
                            usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", 0),
                            usage.get("total_tokens", 0),
                        )
                    continue

                choice = choices[0]
                delta = choice.get("delta", {})
                finish = choice.get("finish_reason")

                # Text content
                text = delta.get("content") or ""
                if text:
                    if not current_text_block:
                        current_text_block = True
                        yield {
                            "_event": "content_block_start",
                            "content_block": {"type": "text", "text": ""},
                        }
                    yield {
                        "_event": "content_block_delta",
                        "delta": {"type": "text_delta", "text": text},
                    }

                # Tool calls (streamed incrementally)
                if delta.get("tool_calls"):
                    for tc_delta in delta["tool_calls"]:
                        idx = tc_delta.get("index", 0)

                        if idx not in tool_blocks:
                            # New tool call starting
                            if current_text_block:
                                yield {"_event": "content_block_stop", "index": 0}
                                current_text_block = False

                            tc_id = tc_delta.get("id", "")
                            tc_name = tc_delta.get("function", {}).get("name", "")
                            tool_blocks[idx] = {
                                "id": tc_id,
                                "name": tc_name,
                                "partial_args": "",
                            }
                            yield {
                                "_event": "content_block_start",
                                "content_block": {
                                    "type": "tool_use",
                                    "id": tc_id,
                                    "name": tc_name,
                                },
                            }
                        else:
                            # Update id/name if provided in later chunks
                            if tc_delta.get("id"):
                                tool_blocks[idx]["id"] = tc_delta["id"]
                            if tc_delta.get("function", {}).get("name"):
                                tool_blocks[idx]["name"] = tc_delta["function"]["name"]

                        # Accumulate arguments
                        args_chunk = tc_delta.get("function", {}).get("arguments", "")
                        if args_chunk:
                            tool_blocks[idx]["partial_args"] += args_chunk
                            yield {
                                "_event": "content_block_delta",
                                "delta": {"type": "input_json_delta", "partial_json": args_chunk},
                            }

                if finish:
                    # Close any open blocks
                    if current_text_block:
                        yield {"_event": "content_block_stop", "index": 0}
                        current_text_block = False
                    for idx in list(tool_blocks):
                        yield {"_event": "content_block_stop", "index": idx}
                    tool_blocks.clear()

                    # Map finish_reason
                    if finish == "tool_calls":
                        stop_reason = "tool_use"
                    elif finish == "stop":
                        stop_reason = "end_turn"
                    elif finish == "length":
                        stop_reason = "max_tokens"
                    else:
                        stop_reason = finish

                    # Log usage if present in final chunk
                    usage = event.get("usage")
                    if usage:
                        log.info(
                            "API usage: input=%d output=%d total=%d",
                            usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", 0),
                            usage.get("total_tokens", 0),
                        )
                    resp_id = event.get("id", "")
                    if resp_id:
                        log.info("API response ← model=%s | id=%s", self.model, resp_id)

        # Emit final message_delta
        yield {
            "_event": "message_delta",
            "delta": {"stop_reason": stop_reason},
        }

    async def call(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """Non-streaming call — consume stream and build Anthropic-compatible response."""
        content: list[dict] = []
        stop_reason = "end_turn"
        current_text = ""
        current_tool: dict | None = None

        async for event in self.stream(messages, system, tools, max_tokens):
            etype = event.get("_event")

            if etype == "content_block_start":
                block = event.get("content_block", {})
                if block.get("type") == "text":
                    current_text = ""
                elif block.get("type") == "tool_use":
                    current_tool = {
                        "type": "tool_use",
                        "id": block["id"],
                        "name": block["name"],
                        "input": {},
                    }

            elif etype == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    current_text += delta.get("text", "")
                elif delta.get("type") == "input_json_delta":
                    if current_tool is not None:
                        current_tool.setdefault("_raw_args", "")
                        current_tool["_raw_args"] += delta.get("partial_json", "")

            elif etype == "content_block_stop":
                if current_tool is not None:
                    raw = current_tool.pop("_raw_args", "{}")
                    try:
                        current_tool["input"] = json.loads(raw)
                    except json.JSONDecodeError:
                        current_tool["input"] = {}
                    content.append(current_tool)
                    current_tool = None
                elif current_text:
                    content.append({"type": "text", "text": current_text})
                    current_text = ""

            elif etype == "message_delta":
                stop_reason = event.get("delta", {}).get("stop_reason", stop_reason)

        if current_text:
            content.append({"type": "text", "text": current_text})

        return {"content": content, "stop_reason": stop_reason}

    async def refresh_auth(self) -> None:
        """API key auth — no refresh needed."""
        pass
