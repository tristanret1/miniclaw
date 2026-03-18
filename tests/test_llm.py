"""Tests for bot.llm — unified LLM entry point."""

from unittest.mock import patch, MagicMock

import bot.llm as llm_mod
from bot.session import SessionManager
from tests.conftest import FakeProvider, make_text_stream_events


class TestLLM:
    async def test_stream_yields_chunks(self, session_db, monkeypatch):
        events = make_text_stream_events("Hello from LLM")
        provider = FakeProvider(stream_events=[events])
        session = SessionManager()

        monkeypatch.setattr(llm_mod, "_provider", provider)
        monkeypatch.setattr(llm_mod, "_session_mgr", session)

        chunks = []
        async for chunk in llm_mod.stream("test:1", "hi"):
            chunks.append(chunk)

        assert "".join(chunks) == "Hello from LLM"

    async def test_reply_collects_all_chunks(self, session_db, monkeypatch):
        events = make_text_stream_events("Complete reply")
        provider = FakeProvider(stream_events=[events])
        session = SessionManager()

        monkeypatch.setattr(llm_mod, "_provider", provider)
        monkeypatch.setattr(llm_mod, "_session_mgr", session)

        result = await llm_mod.reply("test:1", "hi")
        assert result == "Complete reply"

    async def test_singletons_created(self, monkeypatch):
        """Singletons are created on first access."""
        monkeypatch.setattr(llm_mod, "_provider", None)
        monkeypatch.setattr(llm_mod, "_session_mgr", None)

        provider = llm_mod._get_provider()
        session = llm_mod._get_session_mgr()

        assert provider is not None
        assert session is not None
        # Second call returns same instance
        assert llm_mod._get_provider() is provider
        assert llm_mod._get_session_mgr() is session

    async def test_singletons_reused(self, monkeypatch):
        """Multiple calls reuse the same provider and session."""
        monkeypatch.setattr(llm_mod, "_provider", None)
        monkeypatch.setattr(llm_mod, "_session_mgr", None)

        p1 = llm_mod._get_provider()
        p2 = llm_mod._get_provider()
        s1 = llm_mod._get_session_mgr()
        s2 = llm_mod._get_session_mgr()
        assert p1 is p2
        assert s1 is s2
