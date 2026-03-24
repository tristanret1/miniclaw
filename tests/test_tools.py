"""Tests for bot.tools — tool execution and routing."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from bot.tools import (
    ALL_TOOLS,
    handle_tool_call,
    run_exec,
    MAX_OUTPUT_CHARS,
)


class TestRunExec:
    async def test_success(self):
        result = await run_exec("echo hello")
        assert "hello" in result

    async def test_exit_code_reported(self):
        result = await run_exec("exit 1")
        assert "exit code" in result

    async def test_stderr_included(self):
        result = await run_exec("echo err >&2")
        assert "err" in result
        assert "stderr" in result

    async def test_timeout(self):
        result = await run_exec("sleep 10", timeout=1)
        assert "Timed out" in result

    async def test_no_output(self):
        result = await run_exec("true")
        assert "exit code 0" in result

    async def test_truncation(self):
        # Generate output exceeding MAX_OUTPUT_CHARS
        cmd = f"python3 -c \"print('x' * {MAX_OUTPUT_CHARS + 1000})\""
        result = await run_exec(cmd)
        assert "truncated" in result
        assert len(result) <= MAX_OUTPUT_CHARS + 200  # some overhead for truncation message

    async def test_workdir(self, tmp_path):
        result = await run_exec("pwd", workdir=str(tmp_path))
        assert str(tmp_path) in result

    async def test_invalid_workdir_ignored(self):
        # Invalid workdir should not crash, falls back to current dir
        result = await run_exec("echo ok", workdir="/nonexistent/path/xyz")
        assert "ok" in result


class TestHandleToolCall:
    async def test_exec_routing(self):
        result = await handle_tool_call("exec", {"command": "echo routing_test"})
        assert "routing_test" in result

    async def test_memory_save_routing(self):
        with patch("bot.tools.memory") as mock_mem:
            mock_mem.save.return_value = "Saved #1"
            result = await handle_tool_call("memory_save", {"content": "test"})
            assert result == "Saved #1"
            mock_mem.save.assert_called_once_with(content="test", tags=None, memory_dir=None)

    async def test_memory_search_routing(self):
        with patch("bot.tools.memory") as mock_mem:
            mock_mem.search.return_value = "found stuff"
            result = await handle_tool_call("memory_search", {"query": "test"})
            assert result == "found stuff"

    async def test_unknown_tool(self):
        result = await handle_tool_call("nonexistent_tool", {})
        assert "Unknown tool" in result

    async def test_claude_code_routing(self):
        with patch("bot.tools.acp") as mock_acp:
            mock_acp.run_prompt = AsyncMock(return_value="code result")
            result = await handle_tool_call("claude_code", {"task": "fix bug"})
            assert result == "code result"


    async def test_google_calendar_routing(self):
        with patch("bot.google_calendar.list_events", return_value=[]) as mock_list, \
             patch("bot.google_calendar.format_events", return_value="No events found for this period.") as mock_fmt:
            result = await handle_tool_call(
                "google_calendar",
                {"action": "list", "date_start": "2026-03-23T00:00:00", "date_end": "2026-03-24T00:00:00"},
            )
            assert "No events found" in result


class TestToolDefinitions:
    def test_all_tools_have_required_fields(self):
        for tool in ALL_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_exec_tool_schema(self):
        exec_tool = next(t for t in ALL_TOOLS if t["name"] == "exec")
        assert "command" in exec_tool["input_schema"]["properties"]
        assert "command" in exec_tool["input_schema"]["required"]

    def test_tool_names_unique(self):
        names = [t["name"] for t in ALL_TOOLS]
        assert len(names) == len(set(names))
