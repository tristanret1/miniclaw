"""Tests for bot.session — SessionManager cache + SQLite persistence."""

import bot.session as session_mod
from bot.session import SessionManager


class TestSessionManager:
    def test_get_history_empty(self, session_db):
        mgr = SessionManager()
        history = mgr.get_history("test:1")
        assert history == []

    def test_append_and_retrieve(self, session_db):
        mgr = SessionManager()
        mgr.append("test:1", "user", "hello")
        mgr.append("test:1", "assistant", "hi there")
        history = mgr.get_history("test:1")
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "hello"}
        assert history[1] == {"role": "assistant", "content": "hi there"}

    def test_persistence_across_instances(self, session_db):
        mgr1 = SessionManager()
        mgr1.append("test:1", "user", "hello")
        mgr1.append("test:1", "assistant", "world")

        # Reset connection to simulate restart
        if session_mod._conn is not None:
            session_mod._conn.close()
            session_mod._conn = None

        mgr2 = SessionManager()
        history = mgr2.get_history("test:1")
        assert len(history) == 2
        assert history[0]["content"] == "hello"

    def test_clear_removes_from_db_and_cache(self, session_db):
        mgr = SessionManager()
        mgr.append("test:1", "user", "hello")
        mgr.append("test:1", "assistant", "hi")
        assert len(mgr.get_history("test:1")) == 2

        deleted = mgr.clear("test:1")
        assert deleted == 2
        assert mgr.get_history("test:1") == []

    def test_cache_hit(self, session_db):
        mgr = SessionManager()
        mgr.append("test:1", "user", "hello")
        # First access loads from DB and caches
        h1 = mgr.get_history("test:1")
        # Second access uses cache (same object)
        h2 = mgr.get_history("test:1")
        assert h1 is h2

    def test_separate_sessions(self, session_db):
        mgr = SessionManager()
        mgr.append("session_a", "user", "a msg")
        mgr.append("session_b", "user", "b msg")
        assert len(mgr.get_history("session_a")) == 1
        assert len(mgr.get_history("session_b")) == 1
        assert mgr.get_history("session_a")[0]["content"] == "a msg"

    def test_append_list_content(self, session_db):
        """Structured content (tool blocks) persists as JSON."""
        mgr = SessionManager()
        # Build a valid tool_use + tool_result pair so sanitization keeps them
        mgr.append("test:1", "user", "run ls")
        mgr.append("test:1", "assistant", [
            {"type": "tool_use", "id": "t1", "name": "exec", "input": {"command": "ls"}},
        ])
        tool_result_content = [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]
        mgr.append("test:1", "user", tool_result_content)

        # Reset to force DB reload
        if session_mod._conn is not None:
            session_mod._conn.close()
            session_mod._conn = None

        mgr2 = SessionManager()
        history = mgr2.get_history("test:1")
        assert len(history) == 3
        assert isinstance(history[2]["content"], list)
        assert history[2]["content"][0]["type"] == "tool_result"

    def test_sanitization_on_load(self, session_db):
        """Malformed tool pairs in DB are sanitized on load."""
        mgr = SessionManager()
        # Directly persist a broken tool_use without matching result
        session_mod._persist("test:1", "user", "hello")
        session_mod._persist("test:1", "assistant", [
            {"type": "tool_use", "id": "t1", "name": "exec", "input": {}},
        ])
        # No tool_result follows — just another user message
        session_mod._persist("test:1", "user", "next")

        # Reset cache + connection
        if session_mod._conn is not None:
            session_mod._conn.close()
            session_mod._conn = None

        mgr2 = SessionManager()
        history = mgr2.get_history("test:1")
        # The orphan tool_use pair should be dropped
        assert not any(
            isinstance(m.get("content"), list) and any(
                b.get("type") == "tool_use" for b in m["content"]
            )
            for m in history
        )

    def test_should_flush_short_history(self, session_db):
        mgr = SessionManager()
        mgr.append("test:1", "user", "short message")
        assert mgr.should_flush("test:1") is False

    def test_mark_flushed_prevents_repeat(self, session_db):
        mgr = SessionManager()
        mgr.mark_flushed("test:1")
        assert mgr.should_flush("test:1") is False


class TestDbFunctions:
    def test_clear_session_empty(self, session_db):
        count = session_mod.clear_session("nonexistent")
        assert count == 0

    def test_persist_and_load(self, session_db):
        session_mod._persist("s1", "user", "msg1")
        session_mod._persist("s1", "assistant", "msg2")
        history = session_mod._load_from_db("s1", limit=10)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_load_respects_limit(self, session_db):
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            session_mod._persist("s1", role, f"msg{i}")
        history = session_mod._load_from_db("s1", limit=5)
        assert len(history) == 5
