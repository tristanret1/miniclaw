"""Tests for bot.provider.codex — message transformation, streaming, and auth."""

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.provider.codex import (
    CodexProvider,
    _to_codex_messages,
    _to_codex_tools,
)


class TestToCodexMessages:
    def test_simple_text(self):
        msgs = [{"role": "user", "content": "hello"}]
        result = _to_codex_messages(msgs, "sys prompt")
        assert result[0] == {"role": "developer", "content": "sys prompt"}
        assert result[1] == {
            "role": "user",
            "content": [{"type": "input_text", "text": "hello"}],
        }

    def test_assistant_text(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello back"},
        ]
        result = _to_codex_messages(msgs, "")
        # No developer message when system is empty
        assert result[0]["role"] == "user"
        assert result[1] == {
            "role": "assistant",
            "content": [{"type": "output_text", "text": "hello back"}],
        }

    def test_image_content(self):
        msgs = [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "url", "url": "https://img.png"}},
                {"type": "text", "text": "describe this"},
            ],
        }]
        result = _to_codex_messages(msgs, "")
        user_msg = result[0]
        assert user_msg["role"] == "user"
        assert len(user_msg["content"]) == 2
        assert user_msg["content"][0] == {"type": "input_image", "image_url": "https://img.png"}
        assert user_msg["content"][1] == {"type": "input_text", "text": "describe this"}

    def test_tool_use_and_result(self):
        msgs = [
            {"role": "user", "content": "list files"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "sure"},
                {"type": "tool_use", "id": "t1", "name": "exec", "input": {"command": "ls"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "file.txt"},
            ]},
        ]
        result = _to_codex_messages(msgs, "")
        # user → assistant text → function_call → function_call_output
        assert result[0]["role"] == "user"
        assert result[1] == {
            "role": "assistant",
            "content": [{"type": "output_text", "text": "sure"}],
        }
        assert result[2] == {
            "type": "function_call",
            "call_id": "t1",
            "name": "exec",
            "arguments": '{"command": "ls"}',
        }
        assert result[3] == {
            "type": "function_call_output",
            "call_id": "t1",
            "output": "file.txt",
        }

    def test_tool_result_with_list_content(self):
        """tool_result with list content should be JSON-serialized."""
        msgs = [
            {"role": "user", "content": "run it"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t2", "name": "exec", "input": {"command": "echo hi"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t2",
                 "content": [{"type": "text", "text": "hi"}]},
            ]},
        ]
        result = _to_codex_messages(msgs, "")
        output_msg = result[2]
        assert output_msg["type"] == "function_call_output"
        assert output_msg["call_id"] == "t2"
        assert output_msg["output"] == '[{"type": "text", "text": "hi"}]'

    def test_system_prompt_as_developer(self):
        result = _to_codex_messages([], "You are helpful")
        assert len(result) == 1
        assert result[0] == {"role": "developer", "content": "You are helpful"}

    def test_empty_system_prompt(self):
        result = _to_codex_messages([], "")
        assert len(result) == 0


class TestToCodexTools:
    def test_converts_anthropic_tools(self):
        tools = [{
            "name": "exec",
            "description": "Run a command",
            "input_schema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        }]
        result = _to_codex_tools(tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["name"] == "exec"
        assert result[0]["description"] == "Run a command"
        assert result[0]["parameters"]["properties"]["command"]["type"] == "string"

    def test_multiple_tools(self):
        tools = [
            {"name": "exec", "description": "run", "input_schema": {"type": "object", "properties": {}}},
            {"name": "memory_save", "description": "save", "input_schema": {"type": "object", "properties": {}}},
        ]
        result = _to_codex_tools(tools)
        assert len(result) == 2
        assert result[0]["name"] == "exec"
        assert result[1]["name"] == "memory_save"


class TestCodexProvider:
    def test_build_body(self):
        provider = CodexProvider(model="gpt-5.3-codex")
        body = provider._build_body(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=[{"name": "exec", "description": "run", "input_schema": {"type": "object", "properties": {}}}],
        )
        assert body["model"] == "gpt-5.3-codex"
        assert body["stream"] is True
        assert body["store"] is False
        assert "input" in body
        assert body["tools"][0]["type"] == "function"

    def test_build_body_no_tools(self):
        provider = CodexProvider(model="gpt-5.3-codex")
        body = provider._build_body(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=None,
        )
        assert "tools" not in body

    def test_headers_with_account_id(self):
        provider = CodexProvider(model="gpt-5.3-codex")
        headers = provider._headers({
            "access_token": "tok",
            "account_id": "acct_123",
        })
        assert headers["Authorization"] == "Bearer tok"
        assert headers["ChatGPT-Account-Id"] == "acct_123"

    def test_headers_without_account_id(self):
        provider = CodexProvider(model="gpt-5.3-codex")
        headers = provider._headers({"access_token": "tok"})
        assert "ChatGPT-Account-Id" not in headers


# ── Helpers for SSE simulation ───────────────────────────────────────────────


class FakeSSEResponse:
    """Simulates an httpx streaming response with SSE lines."""

    def __init__(self, lines: list[str], status_code: int = 200):
        self.status_code = status_code
        self._lines = lines

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b"error body"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeHTTPClient:
    """Fake httpx.AsyncClient that returns a FakeSSEResponse."""

    def __init__(self, response: FakeSSEResponse):
        self._response = response
        self.is_closed = False

    @asynccontextmanager
    async def stream(self, method, url, **kwargs):
        yield self._response


def _sse_line(event_data: dict) -> str:
    return f"data: {json.dumps(event_data)}"


def _make_text_sse_lines(text: str) -> list[str]:
    """Build SSE lines for a simple text response."""
    return [
        _sse_line({"type": "response.output_text.delta", "delta": text}),
        _sse_line({"type": "response.completed"}),
        "data: [DONE]",
    ]


def _make_tool_call_sse_lines(
    item_id: str, call_id: str, name: str, arguments: dict
) -> list[str]:
    """Build SSE lines for a function call response."""
    return [
        _sse_line({
            "type": "response.output_item.added",
            "item": {"type": "function_call", "id": item_id, "call_id": call_id, "name": name},
        }),
        _sse_line({
            "type": "response.function_call_arguments.delta",
            "item_id": item_id,
            "delta": json.dumps(arguments),
        }),
        _sse_line({
            "type": "response.output_item.done",
            "item": {"type": "function_call", "id": item_id},
        }),
        _sse_line({"type": "response.completed"}),
        "data: [DONE]",
    ]


FAKE_CREDS = {
    "access_token": "test-token",
    "refresh_token": "test-refresh",
    "expires_at": time.time() + 3600,
    "account_id": "acct_test",
}


# ── Streaming tests ──────────────────────────────────────────────────────────


class TestCodexStreaming:
    """Tests for CodexProvider.stream() SSE event translation."""

    @pytest.fixture(autouse=True)
    def _patch_auth(self, monkeypatch):
        monkeypatch.setattr(
            "bot.provider.codex.load_credentials", lambda: FAKE_CREDS
        )
        monkeypatch.setattr(
            "bot.provider.codex.refresh_token", lambda c: FAKE_CREDS
        )

    async def test_text_stream(self):
        """Text output delta events are translated to Anthropic-compatible events."""
        provider = CodexProvider(model="gpt-5.3-codex")
        sse_resp = FakeSSEResponse(_make_text_sse_lines("Hello world"))
        provider._http = FakeHTTPClient(sse_resp)

        events = []
        async for ev in provider.stream([{"role": "user", "content": "hi"}], "sys"):
            events.append(ev)

        # Should have: content_block_start, content_block_delta, content_block_stop, message_delta
        types = [e["_event"] for e in events]
        assert "content_block_start" in types
        assert "content_block_delta" in types
        assert "message_delta" in types

        # Text content should be in delta
        text_deltas = [e for e in events if e.get("_event") == "content_block_delta"]
        assert text_deltas[0]["delta"]["text"] == "Hello world"

        # Stop reason should be end_turn (no tool calls)
        msg_delta = [e for e in events if e.get("_event") == "message_delta"][0]
        assert msg_delta["delta"]["stop_reason"] == "end_turn"

    async def test_tool_call_stream(self):
        """Function call events are translated to tool_use blocks."""
        provider = CodexProvider(model="gpt-5.3-codex")
        sse_lines = _make_tool_call_sse_lines(
            item_id="item_1", call_id="call_1", name="exec",
            arguments={"command": "ls -la"},
        )
        provider._http = FakeHTTPClient(FakeSSEResponse(sse_lines))

        events = []
        async for ev in provider.stream([{"role": "user", "content": "list files"}], "sys"):
            events.append(ev)

        types = [e["_event"] for e in events]
        assert "content_block_start" in types
        assert "content_block_delta" in types
        assert "content_block_stop" in types

        # Tool use block should have correct name
        start_events = [e for e in events if e.get("_event") == "content_block_start"]
        tool_start = [e for e in start_events if e["content_block"].get("type") == "tool_use"]
        assert len(tool_start) == 1
        assert tool_start[0]["content_block"]["name"] == "exec"
        assert tool_start[0]["content_block"]["id"] == "call_1"

        # Stop reason should be tool_use
        msg_delta = [e for e in events if e.get("_event") == "message_delta"][0]
        assert msg_delta["delta"]["stop_reason"] == "tool_use"

    async def test_mixed_text_then_tool(self):
        """Text followed by tool call: text block is closed before tool block."""
        provider = CodexProvider(model="gpt-5.3-codex")
        sse_lines = [
            # Text first
            _sse_line({"type": "response.output_text.delta", "delta": "Sure, "}),
            _sse_line({"type": "response.output_text.delta", "delta": "let me check."}),
            # Then tool call
            _sse_line({
                "type": "response.output_item.added",
                "item": {"type": "function_call", "id": "item_2", "call_id": "c2", "name": "exec"},
            }),
            _sse_line({
                "type": "response.function_call_arguments.delta",
                "item_id": "item_2",
                "delta": '{"command":"ls"}',
            }),
            _sse_line({
                "type": "response.output_item.done",
                "item": {"type": "function_call", "id": "item_2"},
            }),
            "data: [DONE]",
        ]
        provider._http = FakeHTTPClient(FakeSSEResponse(sse_lines))

        events = []
        async for ev in provider.stream([{"role": "user", "content": "list"}], "sys"):
            events.append(ev)

        types = [e["_event"] for e in events]
        # Text block start → text deltas → text block stop → tool start → tool delta → tool stop → message_delta
        # The text block should be stopped before tool block starts
        stop_indices = [i for i, e in enumerate(events) if e["_event"] == "content_block_stop"]
        tool_start_idx = next(
            i for i, e in enumerate(events)
            if e.get("_event") == "content_block_start"
            and e["content_block"].get("type") == "tool_use"
        )
        # At least one stop before tool_start (closing the text block)
        assert any(si < tool_start_idx for si in stop_indices)

    async def test_empty_and_junk_lines_skipped(self):
        """Non-data lines and malformed JSON are gracefully skipped."""
        provider = CodexProvider(model="gpt-5.3-codex")
        sse_lines = [
            "",                                    # empty line
            "event: ping",                         # non-data line
            "data: not-valid-json",                # malformed JSON
            _sse_line({"type": "response.output_text.delta", "delta": "ok"}),
            _sse_line({"type": "response.completed"}),
            "data: [DONE]",
        ]
        provider._http = FakeHTTPClient(FakeSSEResponse(sse_lines))

        events = []
        async for ev in provider.stream([{"role": "user", "content": "hi"}], "sys"):
            events.append(ev)

        text_deltas = [e for e in events if e.get("_event") == "content_block_delta"]
        assert len(text_deltas) == 1
        assert text_deltas[0]["delta"]["text"] == "ok"

    async def test_stream_error_event_raises(self):
        """An error event in the stream raises RuntimeError."""
        provider = CodexProvider(model="gpt-5.3-codex")
        sse_lines = [
            _sse_line({"type": "error", "message": "rate limit exceeded"}),
        ]
        provider._http = FakeHTTPClient(FakeSSEResponse(sse_lines))

        with pytest.raises(RuntimeError, match="rate limit exceeded"):
            async for _ in provider.stream([{"role": "user", "content": "hi"}], "sys"):
                pass

    async def test_stream_401_raises(self):
        """401 response raises RuntimeError for auth expiry."""
        provider = CodexProvider(model="gpt-5.3-codex")
        provider._http = FakeHTTPClient(FakeSSEResponse([], status_code=401))

        with pytest.raises(RuntimeError, match="Auth expired"):
            async for _ in provider.stream([{"role": "user", "content": "hi"}], "sys"):
                pass

    async def test_stream_non_200_raises(self):
        """Non-200 response raises RuntimeError with status code."""
        provider = CodexProvider(model="gpt-5.3-codex")
        provider._http = FakeHTTPClient(FakeSSEResponse([], status_code=429))

        with pytest.raises(RuntimeError, match="429"):
            async for _ in provider.stream([{"role": "user", "content": "hi"}], "sys"):
                pass


# ── Call (non-streaming) tests ───────────────────────────────────────────────


class TestCodexCall:
    """Tests for CodexProvider.call() which consumes the stream."""

    @pytest.fixture(autouse=True)
    def _patch_auth(self, monkeypatch):
        monkeypatch.setattr(
            "bot.provider.codex.load_credentials", lambda: FAKE_CREDS
        )

    async def test_call_text_response(self):
        """call() returns Anthropic-compatible response for text output."""
        provider = CodexProvider(model="gpt-5.3-codex")
        provider._http = FakeHTTPClient(
            FakeSSEResponse(_make_text_sse_lines("Hello!"))
        )

        result = await provider.call(
            [{"role": "user", "content": "hi"}], "sys"
        )

        assert result["stop_reason"] == "end_turn"
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello!"

    async def test_call_tool_use_response(self):
        """call() returns tool_use blocks with parsed JSON input."""
        provider = CodexProvider(model="gpt-5.3-codex")
        provider._http = FakeHTTPClient(
            FakeSSEResponse(_make_tool_call_sse_lines(
                "item_1", "call_1", "exec", {"command": "pwd"},
            ))
        )

        result = await provider.call(
            [{"role": "user", "content": "where am I"}], "sys"
        )

        assert result["stop_reason"] == "tool_use"
        assert len(result["content"]) == 1
        tool_block = result["content"][0]
        assert tool_block["type"] == "tool_use"
        assert tool_block["name"] == "exec"
        assert tool_block["id"] == "call_1"
        assert tool_block["input"] == {"command": "pwd"}

    async def test_call_malformed_tool_args_fallback(self):
        """call() handles malformed JSON in tool arguments gracefully."""
        provider = CodexProvider(model="gpt-5.3-codex")
        sse_lines = [
            _sse_line({
                "type": "response.output_item.added",
                "item": {"type": "function_call", "id": "item_1", "call_id": "c1", "name": "exec"},
            }),
            _sse_line({
                "type": "response.function_call_arguments.delta",
                "item_id": "item_1",
                "delta": "{broken json",
            }),
            _sse_line({
                "type": "response.output_item.done",
                "item": {"type": "function_call", "id": "item_1"},
            }),
            "data: [DONE]",
        ]
        provider._http = FakeHTTPClient(FakeSSEResponse(sse_lines))

        result = await provider.call(
            [{"role": "user", "content": "test"}], "sys"
        )

        # Should fallback to empty dict for malformed args
        assert result["content"][0]["input"] == {}


# ── Auth tests ───────────────────────────────────────────────────────────────


class TestCodexAuth:
    """Tests for CodexProvider authentication and refresh logic."""

    def test_get_auth_no_credentials_raises(self):
        """_get_auth raises when no credentials file exists."""
        provider = CodexProvider(model="gpt-5.3-codex")
        with patch("bot.provider.codex.load_credentials", return_value=None):
            with pytest.raises(RuntimeError, match="not authenticated"):
                provider._get_auth()

    def test_get_auth_valid_token_no_refresh(self):
        """_get_auth returns creds without refreshing when token is valid."""
        provider = CodexProvider(model="gpt-5.3-codex")
        creds = {**FAKE_CREDS, "expires_at": time.time() + 3600}
        with patch("bot.provider.codex.load_credentials", return_value=creds) as load_mock:
            with patch("bot.provider.codex.refresh_token") as refresh_mock:
                result = provider._get_auth()
                assert result == creds
                refresh_mock.assert_not_called()

    def test_get_auth_expired_triggers_refresh(self):
        """_get_auth refreshes when token is expired."""
        provider = CodexProvider(model="gpt-5.3-codex")
        expired_creds = {**FAKE_CREDS, "expires_at": time.time() - 100}
        refreshed = {**FAKE_CREDS, "expires_at": time.time() + 3600}
        with patch("bot.provider.codex.load_credentials", return_value=expired_creds):
            with patch("bot.provider.codex.refresh_token", return_value=refreshed) as refresh_mock:
                result = provider._get_auth()
                refresh_mock.assert_called_once_with(expired_creds)
                assert result == refreshed

    async def test_refresh_auth_with_token(self):
        """refresh_auth() calls refresh_token when refresh token exists."""
        provider = CodexProvider(model="gpt-5.3-codex")
        with patch("bot.provider.codex.load_credentials", return_value=FAKE_CREDS):
            with patch("bot.provider.codex.refresh_token") as refresh_mock:
                await provider.refresh_auth()
                refresh_mock.assert_called_once_with(FAKE_CREDS)

    async def test_refresh_auth_no_token_raises(self):
        """refresh_auth() raises when no refresh token available."""
        provider = CodexProvider(model="gpt-5.3-codex")
        with patch("bot.provider.codex.load_credentials", return_value={"access_token": "t"}):
            with pytest.raises(RuntimeError, match="No Codex refresh token"):
                await provider.refresh_auth()

    async def test_refresh_auth_no_creds_raises(self):
        """refresh_auth() raises when no credentials at all."""
        provider = CodexProvider(model="gpt-5.3-codex")
        with patch("bot.provider.codex.load_credentials", return_value=None):
            with pytest.raises(RuntimeError, match="No Codex refresh token"):
                await provider.refresh_auth()
