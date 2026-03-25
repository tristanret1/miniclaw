"""Tests for bot.processor — StreamProcessor tool loop and content accumulation."""

from unittest.mock import patch, AsyncMock

from bot.processor import StreamProcessor
from bot.session import SessionManager
from tests.conftest import FakeProvider, make_text_stream_events, make_tool_use_stream_events


class TestStreamProcessor:
    async def test_simple_text_response(self, session_db, make_text_events):
        events = make_text_events("Hello world")
        provider = FakeProvider(stream_events=[events])
        session = SessionManager()

        processor = StreamProcessor(provider, session, "test:1")
        chunks = []
        async for chunk in processor.process("hi"):
            chunks.append(chunk)

        assert "".join(chunks) == "Hello world"

    async def test_session_appended(self, session_db, make_text_events):
        events = make_text_events("reply")
        provider = FakeProvider(stream_events=[events])
        session = SessionManager()

        processor = StreamProcessor(provider, session, "test:1")
        async for _ in processor.process("user msg"):
            pass

        history = await session.get_history("test:1")
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "user msg"
        assert history[1]["role"] == "assistant"

    async def test_tool_use_loop(self, session_db, make_text_events, make_tool_events):
        """Tool use triggers tool execution and re-queries provider."""
        tool_events = make_tool_events("t1", "exec", {"command": "ls"})
        text_events = make_text_events("Here are the files")
        provider = FakeProvider(stream_events=[tool_events, text_events])
        session = SessionManager()

        with patch("bot.processor.handle_tool_call", new_callable=AsyncMock) as mock_tool:
            mock_tool.return_value = "file.txt"

            processor = StreamProcessor(provider, session, "test:1")
            chunks = []
            async for chunk in processor.process("list files"):
                chunks.append(chunk)

            assert "".join(chunks) == "Here are the files"
            mock_tool.assert_called_once_with("exec", {"command": "ls"}, memory_dir=None, agent_name="default")

    async def test_tool_call_error_handling(self, session_db, make_tool_events, make_text_events):
        """Tool execution failure sends error result back to provider."""
        tool_events = make_tool_events("t1", "exec", {"command": "bad"})
        text_events = make_text_events("Sorry about that")
        provider = FakeProvider(stream_events=[tool_events, text_events])
        session = SessionManager()

        with patch("bot.processor.handle_tool_call", new_callable=AsyncMock) as mock_tool:
            mock_tool.side_effect = RuntimeError("command failed")

            processor = StreamProcessor(provider, session, "test:1")
            chunks = []
            async for chunk in processor.process("run bad command"):
                chunks.append(chunk)

            # Should still get a response (error result sent to provider, which responds)
            assert "".join(chunks) == "Sorry about that"

    async def test_max_tool_rounds(self, session_db, make_tool_events):
        """Stops after MAX_TOOL_ROUNDS with a message."""
        # Create 21 rounds of tool use (exceeds MAX_TOOL_ROUNDS=20)
        tool_events = make_tool_events("t1", "exec", {"command": "loop"})
        provider = FakeProvider(stream_events=[tool_events] * 25)
        session = SessionManager()

        with patch("bot.processor.handle_tool_call", new_callable=AsyncMock) as mock_tool:
            mock_tool.return_value = "ok"
            # Also patch MAX_TOOL_ROUNDS to a small number for faster test
            with patch("bot.processor.MAX_TOOL_ROUNDS", 3):
                processor = StreamProcessor(provider, session, "test:1")
                chunks = []
                async for chunk in processor.process("loop forever"):
                    chunks.append(chunk)

                result = "".join(chunks)
                assert "too many tool calls" in result.lower()

    async def test_auth_expired_fallback(self, session_db):
        """Auth expiry during stream falls back to non-streaming call."""

        class AuthExpiredProvider(FakeProvider):
            async def stream(self, messages, system, tools=None, max_tokens=4096):
                raise RuntimeError("Auth expired during stream")
                # Make it an async generator
                yield  # pragma: no cover

            async def call(self, messages, system, tools=None, max_tokens=4096):
                return {
                    "content": [{"type": "text", "text": "fallback response"}],
                    "stop_reason": "end_turn",
                }

        provider = AuthExpiredProvider()
        session = SessionManager()
        processor = StreamProcessor(provider, session, "test:1")
        chunks = []
        async for chunk in processor.process("hi"):
            chunks.append(chunk)

        assert "fallback response" in "".join(chunks)


class TestAutoFlush:
    async def test_auto_flush_triggered(self, session_db, make_text_events, monkeypatch):
        """When should_flush returns True, flush task is created."""
        events = make_text_events("ok")
        provider = FakeProvider(stream_events=[events])
        session = SessionManager()

        # Force should_flush to return True (async)
        async def _always_flush(key):
            return True
        monkeypatch.setattr(session, "should_flush", _always_flush)

        import asyncio
        created_tasks = []
        original_create_task = asyncio.create_task

        def track_create_task(coro):
            task = original_create_task(coro)
            created_tasks.append(task)
            return task

        with patch("bot.processor.asyncio.create_task", side_effect=track_create_task):
            processor = StreamProcessor(provider, session, "test:1")
            async for _ in processor.process("trigger flush"):
                pass

        assert len(created_tasks) == 1
        # Cancel the background task to avoid warnings
        for t in created_tasks:
            t.cancel()
