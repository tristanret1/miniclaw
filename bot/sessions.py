"""Conversation persistence — SQLite-backed session history."""

import json
import sqlite3
from pathlib import Path

from bot.config import WORKSPACE_DIR
from bot.logger import get_logger

log = get_logger("sessions")

DB_PATH = WORKSPACE_DIR / "sessions.db"

# Reusable connection (SQLite is single-threaded anyway)
_conn: sqlite3.Connection | None = None


def _get_db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH))
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _ensure_schema(_conn)
    return _conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_key, id);
    """)
    conn.commit()


def load_history(session_key: str, limit: int) -> list[dict]:
    """Load the most recent messages for a session."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT role, content FROM ("
        "  SELECT role, content, id FROM messages"
        "  WHERE session_key = ? ORDER BY id DESC LIMIT ?"
        ") ORDER BY id ASC",
        (session_key, limit),
    ).fetchall()

    history = []
    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        history.append({"role": row["role"], "content": content})

    if history:
        log.info("loaded %d messages for session %s", len(history), session_key)
    return history


def append_message(session_key: str, role: str, content: str | list | dict) -> None:
    """Persist a single message."""
    if isinstance(content, (list, dict)):
        content_str = json.dumps(content, ensure_ascii=False)
    else:
        content_str = content

    conn = _get_db()
    conn.execute(
        "INSERT INTO messages (session_key, role, content) VALUES (?, ?, ?)",
        (session_key, role, content_str),
    )
    conn.commit()


def clear_session(session_key: str) -> int:
    """Delete all messages for a session. Returns count deleted."""
    conn = _get_db()
    cur = conn.execute("DELETE FROM messages WHERE session_key = ?", (session_key,))
    conn.commit()
    log.info("cleared %d messages for session %s", cur.rowcount, session_key)
    return cur.rowcount
