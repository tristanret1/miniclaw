"""Tests for bot.provider.codex — message transformation and response conversion."""

import json
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
