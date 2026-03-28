"""Codex provider — OpenAI Responses API with OAuth (ChatGPT subscription)."""

import json
import time
from collections.abc import AsyncIterator

from bot.oauth.codex import (
    CODEX_API_ENDPOINT,
    load_credentials,
    refresh_token,
)
from bot.logger import get_logger
from bot.message import Message
from bot.provider.base import BaseProvider

log = get_logger("codex")


def _to_codex_messages(messages: list[Message], system: str) -> list[dict]:
    """Convert internal Message format to OpenAI Responses API input format.

    Mapping:
      user text         → {role: "user", content: [{type: "input_text", text}]}
      user image        → {role: "user", content: [{type: "input_image", image_url}]}
      assistant text    → {role: "assistant", content: [{type: "output_text", text}]}
      assistant tool_use → {type: "function_call", call_id, name, arguments}
      user tool_result  → {type: "function_call_output", call_id, output}
    """
    result: list[dict] = []

    # System prompt as developer message
    if system:
        result.append({"role": "developer", "content": system})

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role == "user":
            if isinstance(content, str):
                result.append({
                    "role": "user",
                    "content": [{"type": "input_text", "text": content}],
                })
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
                                "type": "function_call_output",
                                "call_id": block["tool_use_id"],
                                "output": str(output),
                            })
                else:
                    # Mixed text + image content
                    parts: list[dict] = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                parts.append({"type": "input_text", "text": block["text"]})
                            elif block.get("type") == "image":
                                source = block.get("source", {})
                                if source.get("type") == "url":
                                    parts.append({"type": "input_image", "image_url": source["url"]})
                    if parts:
                        result.append({"role": "user", "content": parts})

        elif role == "assistant":
            if isinstance(content, str):
                result.append({
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": content}],
                })
            elif isinstance(content, list):
                # May contain text blocks and tool_use blocks
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            result.append({
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": block["text"]}],
                            })
                        elif block.get("type") == "tool_use":
                            args = block.get("input", {})
                            result.append({
                                "type": "function_call",
                                "call_id": block["id"],
                                "name": block["name"],
                                "arguments": json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args),
                            })

    return result


def _to_codex_tools(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool definitions to OpenAI function tool format.

    Anthropic:  {name, description, input_schema: {type, properties, required}}
    OpenAI:     {type: "function", name, description, parameters: {type, properties, required}}
    """
    result: list[dict] = []
    for tool in tools:
        result.append({
            "type": "function",
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        })
    return result


class CodexProvider(BaseProvider):
    """OpenAI Codex provider using the Responses API with ChatGPT subscription OAuth."""

    def __init__(self, model: str):
        super().__init__()
        self.model = model

    def _get_auth(self) -> dict:
        """Get current credentials, refreshing if expired."""
        creds = load_credentials()
        if not creds:
            raise RuntimeError("Codex not authenticated. Run: python setup.py")

        # Auto-refresh if expired
        expires_at = creds.get("expires_at", 0)
        if time.time() >= expires_at:
            log.info("refreshing codex access token")
            creds = refresh_token(creds)

        return creds

    def _headers(self, creds: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {creds['access_token']}",
            "Content-Type": "application/json",
        }
        account_id = creds.get("account_id")
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id
        return headers

    def _build_body(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None,
    ) -> dict:
        body: dict = {
            "model": self.model,
            "instructions": system or "You are a helpful assistant.",
            "input": _to_codex_messages(messages, ""),  # system via instructions, not input
            "stream": True,  # Codex API requires streaming
            "store": False,
        }
        if tools:
            body["tools"] = _to_codex_tools(tools)
        return body

    async def stream(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[dict]:
        """Stream via Codex Responses API, yield events in Anthropic-compatible format.

        Translates Codex SSE events to the same event format that StreamProcessor expects:
        - content_block_start, content_block_delta, content_block_stop, message_delta
        """
        creds = self._get_auth()
        body = self._build_body(messages, system, tools)
        client = self._get_client()

        async with client.stream(
            "POST", CODEX_API_ENDPOINT, json=body, headers=self._headers(creds)
        ) as resp:
            if resp.status_code == 401:
                raise RuntimeError("Auth expired during stream")
            if resp.status_code != 200:
                text = await resp.aread()
                raise RuntimeError(f"Codex API error ({resp.status_code}): {text.decode()}")

            # State for translating Codex events → Anthropic-compatible events
            current_text_block = False
            current_tool_blocks: dict[str, dict] = {}  # item_id → {id, name, partial_args}
            stop_reason = "end_turn"

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")

                # Text output streaming
                if etype == "response.output_text.delta":
                    if not current_text_block:
                        current_text_block = True
                        yield {
                            "_event": "content_block_start",
                            "content_block": {"type": "text", "text": ""},
                        }
                    yield {
                        "_event": "content_block_delta",
                        "delta": {"type": "text_delta", "text": event.get("delta", "")},
                    }

                # Function call started
                elif etype == "response.output_item.added":
                    item = event.get("item", {})
                    if item.get("type") == "function_call":
                        item_id = item.get("id", "")
                        current_tool_blocks[item_id] = {
                            "id": item.get("call_id", item_id),
                            "name": item.get("name", ""),
                            "partial_args": "",
                        }
                        # Close text block if open
                        if current_text_block:
                            yield {"_event": "content_block_stop", "index": 0}
                            current_text_block = False
                        yield {
                            "_event": "content_block_start",
                            "content_block": {
                                "type": "tool_use",
                                "id": current_tool_blocks[item_id]["id"],
                                "name": current_tool_blocks[item_id]["name"],
                            },
                        }

                # Function call arguments streaming
                elif etype == "response.function_call_arguments.delta":
                    item_id = event.get("item_id", "")
                    delta = event.get("delta", "")
                    if item_id in current_tool_blocks:
                        current_tool_blocks[item_id]["partial_args"] += delta
                        yield {
                            "_event": "content_block_delta",
                            "delta": {"type": "input_json_delta", "partial_json": delta},
                        }

                # Item completed
                elif etype == "response.output_item.done":
                    item = event.get("item", {})
                    if item.get("type") == "function_call":
                        item_id = item.get("id", "")
                        if item_id in current_tool_blocks:
                            del current_tool_blocks[item_id]
                        yield {"_event": "content_block_stop", "index": 0}
                        stop_reason = "tool_use"

                # Response completed
                elif etype in ("response.completed", "response.incomplete"):
                    if current_text_block:
                        yield {"_event": "content_block_stop", "index": 0}
                        current_text_block = False

                # Error
                elif etype == "error":
                    error_msg = event.get("message", "Unknown error")
                    raise RuntimeError(f"Codex stream error: {error_msg}")

            # Emit final message_delta with stop_reason
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
        """Non-streaming call via Codex Responses API.

        Codex API requires streaming, so we consume the stream and build
        the response in Anthropic-compatible format.
        """
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

        # Flush any remaining text
        if current_text:
            content.append({"type": "text", "text": current_text})

        return {"content": content, "stop_reason": stop_reason}

    async def refresh_auth(self) -> None:
        creds = load_credentials()
        if creds and creds.get("refresh_token"):
            refresh_token(creds)
        else:
            raise RuntimeError("No Codex refresh token available")


