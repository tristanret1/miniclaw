"""Session management — in-memory cache + SQLite/PostgreSQL persistence."""

import json
import sqlite3
from pathlib import Path

from bot.config import get_config, WORKSPACE_DIR
from bot.storage.db import use_postgres
from bot.logger import get_logger
from bot.message import Content, Message
from bot.provider.transform import sanitize, strip_tool_blocks

log = get_logger("session")

DEFAULT_DB_PATH = WORKSPACE_DIR / "sessions.db"

# Per-path connection cache
_conns: dict[str, sqlite3.Connection] = {}


def _get_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = str(db_path or DEFAULT_DB_PATH)
    if path not in _conns:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _ensure_schema(conn)
        _conns[path] = conn
    return _conns[path]


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


async def _load_from_db(session_key: str, limit: int, db_path: Path | None = None) -> list[Message]:
    """Load the most recent messages for a session from DB."""
    if use_postgres():
        return await _pg_load(session_key, limit)

    conn = _get_db(db_path)
    rows = conn.execute(
        "SELECT role, content FROM ("
        "  SELECT role, content, id FROM messages"
        "  WHERE session_key = ? ORDER BY id DESC LIMIT ?"
        ") ORDER BY id ASC",
        (session_key, limit),
    ).fetchall()

    history: list[Message] = []
    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        # Ensure content is str or list/dict — coerce bare scalars (int, float)
        if not isinstance(content, (str, list, dict)):
            content = str(content)
        history.append({"role": row["role"], "content": content})

    if history:
        log.info("loaded %d messages for session %s", len(history), session_key)
    return history


async def _pg_load(session_key: str, limit: int) -> list[Message]:
    """Load recent messages from PostgreSQL."""
    from bot.storage.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, content FROM ("
            "  SELECT role, content, id FROM messages"
            "  WHERE session_key = $1 ORDER BY id DESC LIMIT $2"
            ") sub ORDER BY id ASC",
            session_key, limit,
        )

    history: list[Message] = []
    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        # Ensure content is str or list/dict — coerce bare scalars (int, float)
        if not isinstance(content, (str, list, dict)):
            content = str(content)
        history.append({"role": row["role"], "content": content})

    if history:
        log.info("loaded %d messages for session %s [pg]", len(history), session_key)
    return history


async def _persist(session_key: str, role: str, content: Content, db_path: Path | None = None) -> None:
    """Persist a single message to DB."""
    if isinstance(content, (list, dict)):
        content_str = json.dumps(content, ensure_ascii=False)
    else:
        content_str = str(content)

    if use_postgres():
        from bot.storage.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO messages (session_key, role, content) VALUES ($1, $2, $3)",
                session_key, role, content_str,
            )
        return

    conn = _get_db(db_path)
    conn.execute(
        "INSERT INTO messages (session_key, role, content) VALUES (?, ?, ?)",
        (session_key, role, content_str),
    )
    conn.commit()


async def clear_session(session_key: str, db_path: Path | None = None) -> int:
    """Delete all messages for a session. Returns count deleted."""
    if use_postgres():
        from bot.storage.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM messages WHERE session_key = $1", session_key)
            count = int(result.split()[-1])  # "DELETE N"
        log.info("cleared %d messages for session %s [pg]", count, session_key)
        return count

    conn = _get_db(db_path)
    cur = conn.execute("DELETE FROM messages WHERE session_key = ?", (session_key,))
    conn.commit()
    log.info("cleared %d messages for session %s", cur.rowcount, session_key)
    return cur.rowcount


class SessionManager:
    """Session management: in-memory cache + SQLite/PostgreSQL persistence."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path
        self._cache: dict[str, list[Message]] = {}
        self._flushed: set[str] = set()

    async def get_history(self, session_key: str) -> list[Message]:
        """Get session history, loading from DB on first access.

        On load: sanitize → strip tool blocks (tool_use/tool_result from
        completed tool loops are useless for future turns, only waste tokens).
        """
        if session_key not in self._cache:
            cfg = get_config()
            raw = await _load_from_db(session_key, cfg.llm.max_history * 2, self._db_path)
            sanitized = sanitize(raw, cfg.llm.provider)
            cleaned = strip_tool_blocks(sanitized)
            if len(raw) != len(cleaned):
                log.info(
                    "loaded session %s: %d raw → %d after sanitize+strip",
                    session_key, len(raw), len(cleaned),
                )
            self._cache[session_key] = cleaned
        return self._cache[session_key]

    async def append(self, session_key: str, role: str, content: Content) -> None:
        """Append a message to cache + DB."""
        history = await self.get_history(session_key)
        history.append({"role": role, "content": content})
        await _persist(session_key, role, content, self._db_path)

    async def trim(self, session_key: str) -> None:
        """Trim history if it exceeds the max limit."""
        history = await self.get_history(session_key)
        before = len(history)
        cfg = get_config()
        limit = cfg.llm.max_history * 2
        if before > limit:
            history[:] = sanitize(history[-limit:], cfg.llm.provider)
            log.warning(
                "trimmed session %s: %d -> %d messages (limit %d)",
                session_key, before, len(history), limit,
            )

    async def clear(self, session_key: str) -> int:
        """Clear session from cache and DB."""
        self._cache.pop(session_key, None)
        self._flushed.discard(session_key)
        return await clear_session(session_key, self._db_path)

    async def should_flush(self, session_key: str) -> bool:
        """Check if auto-flush should trigger for this session."""
        if session_key in self._flushed:
            return False
        from bot.storage.memory import should_flush as check_flush
        return check_flush(await self.get_history(session_key))

    async def replace_recent(self, session_key: str, count: int, role: str, content: Content) -> None:
        """Delete the last *count* persisted messages and insert one replacement.

        Used to collapse tool-loop intermediate messages (tool_use / tool_result)
        into a single final assistant answer after the loop completes.
        Updates both in-memory cache and DB.
        """
        history = await self.get_history(session_key)
        if count <= 0 or count > len(history):
            return

        # In-memory: replace tail
        history[-count:] = [{"role": role, "content": content}]

        # DB: delete last N rows for this session, then insert replacement
        if use_postgres():
            await self._pg_replace_recent(session_key, count, role, content)
        else:
            conn = _get_db(self._db_path)
            conn.execute(
                "DELETE FROM messages WHERE id IN ("
                "  SELECT id FROM messages WHERE session_key = ? ORDER BY id DESC LIMIT ?"
                ")",
                (session_key, count),
            )
            conn.commit()
            await _persist(session_key, role, content, self._db_path)

        log.info("collapsed %d messages → 1 for session %s", count, session_key)

    async def _pg_replace_recent(self, session_key: str, count: int, role: str, content: Content) -> None:
        from bot.storage.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM messages WHERE id IN ("
                "  SELECT id FROM messages WHERE session_key = $1 ORDER BY id DESC LIMIT $2"
                ")",
                session_key, count,
            )
        await _persist(session_key, role, content, self._db_path)

    def mark_flushed(self, session_key: str) -> None:
        self._flushed.add(session_key)
