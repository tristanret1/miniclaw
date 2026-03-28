"""Memory system — SQLite + FTS5 (BM25) + optional vector embeddings (hybrid search).

Supports PostgreSQL backend when DATABASE_URL is set (via bot.db).
"""

import json
import sqlite3
import struct
import time
from datetime import date, datetime
from pathlib import Path

import httpx

from bot.config import get_secrets, WORKSPACE_DIR
from bot.constants import (
    BM25_WEIGHT,
    EMBEDDING_MODEL,
    MEMORY_CHARS_PER_TOKEN as CHARS_PER_TOKEN,
    MEMORY_CHUNK_OVERLAP as CHUNK_OVERLAP,
    MEMORY_CHUNK_TOKENS as CHUNK_TOKENS,
    OPENAI_EMBEDDINGS_URL,
    VECTOR_WEIGHT,
    AUTO_FLUSH_CHAR_THRESHOLD as FLUSH_THRESHOLD_CHARS,
)
from bot.logger import get_logger

log = get_logger("memory")

DEFAULT_MEMORY_DIR = WORKSPACE_DIR / "memory"
DEFAULT_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DEFAULT_MEMORY_DIR / "memory.db"


# ── SQLite setup ──────────────────────────────────────────────────────────────

def _get_db(memory_dir: Path | None = None) -> sqlite3.Connection:
    db_path = (memory_dir / "memory.db") if memory_dir else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            tags TEXT,
            source TEXT,
            created_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            content,
            tags,
            content='memories',
            content_rowid='id',
            tokenize='unicode61'
        );

        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content, tags)
            VALUES (new.id, new.content, new.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, tags)
            VALUES ('delete', old.id, old.content, old.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, tags)
            VALUES ('delete', old.id, old.content, old.tags);
            INSERT INTO memories_fts(rowid, content, tags)
            VALUES (new.id, new.content, new.tags);
        END;

        CREATE TABLE IF NOT EXISTS embeddings (
            memory_id INTEGER PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
            vector BLOB NOT NULL
        );
    """)
    conn.commit()


# ── Embedding helpers ─────────────────────────────────────────────────────────

def _has_embeddings() -> bool:
    return bool(get_secrets()["OPENAI_API_KEY"])


def _get_embedding(text: str) -> list[float] | None:
    """Get embedding from OpenAI API. Returns None on failure."""
    openai_api_key = get_secrets()["OPENAI_API_KEY"]
    if not openai_api_key:
        return None

    try:
        resp = httpx.post(
            OPENAI_EMBEDDINGS_URL,
            json={"input": text, "model": EMBEDDING_MODEL},
            headers={"Authorization": f"Bearer {openai_api_key}"},
            timeout=30,
        )
        if resp.status_code != 200:
            log.warning("embedding API error (%d): %s", resp.status_code, resp.text[:200])
            return None
        return resp.json()["data"][0]["embedding"]
    except Exception as e:
        log.warning("embedding request failed: %s", e)
        return None


def _pack_vector(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack_vector(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Markdown file persistence (keeps human-readable daily logs) ───────────────

def _append_to_daily_log(content: str, tags: list[str] | None, memory_dir: Path | None = None) -> str:
    """Also write to daily Markdown for human readability."""
    mem_dir = memory_dir or DEFAULT_MEMORY_DIR
    mem_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    filepath = mem_dir / f"{today}.md"

    tag_line = ""
    if tags:
        tag_line = f"  tags: {', '.join(tags)}\n"

    entry = f"- {content}\n{tag_line}"
    is_new = not filepath.exists() or filepath.stat().st_size == 0
    with open(filepath, "a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# {today}\n\n")
        f.write(entry + "\n")

    return filepath.name


# ── Public API ────────────────────────────────────────────────────────────────

async def save(content: str, tags: list[str] | None = None, source: str = "agent",
               memory_dir: Path | None = None, agent_name: str = "default") -> str:
    """Save a memory entry to DB + daily Markdown log."""
    from bot.storage.db import use_postgres

    if use_postgres():
        return await _pg_save(content, tags, source, memory_dir, agent_name)
    return _sqlite_save(content, tags, source, memory_dir)


def _sqlite_save(content: str, tags: list[str] | None, source: str,
                 memory_dir: Path | None) -> str:
    """Save via SQLite (original path)."""
    now = datetime.now().isoformat()
    tags_str = ", ".join(tags) if tags else ""

    conn = _get_db(memory_dir)
    try:
        cur = conn.execute(
            "INSERT INTO memories (content, tags, source, created_at) VALUES (?, ?, ?, ?)",
            (content, tags_str, source, now),
        )
        memory_id = cur.lastrowid

        vec = _get_embedding(content)
        if vec:
            conn.execute(
                "INSERT INTO embeddings (memory_id, vector) VALUES (?, ?)",
                (memory_id, _pack_vector(vec)),
            )

        conn.commit()
    finally:
        conn.close()

    logfile = _append_to_daily_log(content, tags, memory_dir)
    log.info("memory saved #%d → %s (%d chars, tags=%s, embedding=%s)",
             memory_id, logfile, len(content), tags, "yes" if vec else "no")
    return f"Saved memory #{memory_id} to {logfile}"


async def _pg_save(content: str, tags: list[str] | None, source: str,
                   memory_dir: Path | None, agent_name: str = "default") -> str:
    """Save via PostgreSQL."""
    from bot.storage.db import get_pool

    tags_str = ", ".join(tags) if tags else ""
    pool = await get_pool()

    async with pool.acquire() as conn:
        memory_id = await conn.fetchval(
            "INSERT INTO memories (content, tags, source, agent_name) VALUES ($1, $2, $3, $4) RETURNING id",
            content, tags_str or None, source, agent_name,
        )

        vec = _get_embedding(content)
        if vec:
            import numpy as np
            await conn.execute(
                "INSERT INTO embeddings (memory_id, vector) VALUES ($1, $2)",
                memory_id, np.array(vec, dtype=np.float32),
            )

    logfile = _append_to_daily_log(content, tags, memory_dir)
    log.info("memory saved #%d → %s (%d chars, tags=%s, embedding=%s) [pg]",
             memory_id, logfile, len(content), tags, "yes" if vec else "no")
    return f"Saved memory #{memory_id} to {logfile}"


async def search(query: str, max_results: int = 10, memory_dir: Path | None = None,
                 agent_name: str = "default") -> str:
    """Hybrid search: BM25 + vector similarity when embeddings available."""
    from bot.storage.db import use_postgres

    if use_postgres():
        return await _pg_search(query, max_results, agent_name)

    conn = _get_db(memory_dir)
    try:
        return _hybrid_search(conn, query, max_results)
    finally:
        conn.close()


def _hybrid_search(conn: sqlite3.Connection, query: str, max_results: int) -> str:
    # BM25 search via FTS5
    bm25_results = _bm25_search(conn, query, max_results * 2)

    # Vector search (if embeddings available)
    vec_results = {}
    query_vec = _get_embedding(query) if _has_embeddings() else None
    if query_vec:
        vec_results = _vector_search(conn, query_vec, max_results * 2)

    if not bm25_results and not vec_results:
        return f"No matches for: {query}"

    # Merge scores
    if vec_results and bm25_results:
        merged = _merge_scores(bm25_results, vec_results, max_results)
        search_type = "hybrid"
    elif vec_results:
        merged = sorted(vec_results.items(), key=lambda x: -x[1])[:max_results]
        search_type = "vector"
    else:
        merged = sorted(bm25_results.items(), key=lambda x: -x[1])[:max_results]
        search_type = "bm25"

    # Fetch full content for top results
    ids = [mid for mid, _ in merged]
    if not ids:
        return f"No matches for: {query}"

    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT id, content, tags, created_at FROM memories WHERE id IN ({placeholders})",
        ids,
    ).fetchall()
    row_map = {r["id"]: r for r in rows}

    lines = []
    for mid, score in merged:
        row = row_map.get(mid)
        if not row:
            continue
        tag_part = f" [{row['tags']}]" if row["tags"] else ""
        lines.append(f"[#{mid} {row['created_at'][:10]}{tag_part} score={score:.2f}] {row['content']}")

    log.info("memory search (%s) '%s' → %d result(s)", search_type, query, len(lines))
    return "\n".join(lines)


def _bm25_search(conn: sqlite3.Connection, query: str, limit: int) -> dict[int, float]:
    """FTS5 BM25 search. Returns {memory_id: normalized_score}."""
    try:
        rows = conn.execute(
            "SELECT rowid, rank FROM memories_fts WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError as e:
        # FTS5 query syntax error — fall back to prefix search
        log.debug("FTS5 match failed (%s), trying prefix", e)
        try:
            prefix_query = " OR ".join(f'"{w}"*' for w in query.split() if w)
            rows = conn.execute(
                "SELECT rowid, rank FROM memories_fts WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                (prefix_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return {}

    if not rows:
        return {}

    # FTS5 rank is negative (lower = better); normalize to 0..1
    scores = {r["rowid"]: -r["rank"] for r in rows}
    max_score = max(scores.values()) or 1.0
    return {mid: s / max_score for mid, s in scores.items()}


def _vector_search(conn: sqlite3.Connection, query_vec: list[float], limit: int) -> dict[int, float]:
    """Brute-force cosine similarity over stored embeddings."""
    rows = conn.execute("SELECT memory_id, vector FROM embeddings").fetchall()
    if not rows:
        return {}

    scored = []
    for row in rows:
        vec = _unpack_vector(row["vector"])
        sim = _cosine_similarity(query_vec, vec)
        scored.append((row["memory_id"], sim))

    scored.sort(key=lambda x: -x[1])
    # Normalize to 0..1
    max_sim = scored[0][1] if scored else 1.0
    if max_sim <= 0:
        return {}
    return {mid: s / max_sim for mid, s in scored[:limit]}


def _merge_scores(
    bm25: dict[int, float], vector: dict[int, float], max_results: int
) -> list[tuple[int, float]]:
    """Weighted merge of BM25 and vector scores."""
    all_ids = set(bm25) | set(vector)
    merged = []
    for mid in all_ids:
        b = bm25.get(mid, 0.0) * BM25_WEIGHT
        v = vector.get(mid, 0.0) * VECTOR_WEIGHT
        merged.append((mid, b + v))
    merged.sort(key=lambda x: -x[1])
    return merged[:max_results]


# ── PostgreSQL search ─────────────────────────────────────────────────────────

async def _pg_search(query: str, max_results: int, agent_name: str = "default") -> str:
    """Hybrid search via PostgreSQL: tsvector FTS + pgvector cosine similarity."""
    from bot.storage.db import get_pool

    pool = await get_pool()

    # BM25-like search via tsvector
    bm25_results: dict[int, float] = {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ts_rank_cd(content_tsv, plainto_tsquery('english', $1)) AS rank
            FROM memories
            WHERE content_tsv @@ plainto_tsquery('english', $1)
              AND agent_name = $3
            ORDER BY rank DESC
            LIMIT $2
            """,
            query, max_results * 2, agent_name,
        )
        if rows:
            max_rank = max(r["rank"] for r in rows) or 1.0
            bm25_results = {r["id"]: r["rank"] / max_rank for r in rows}

    # Vector search (if embeddings available)
    vec_results: dict[int, float] = {}
    query_vec = _get_embedding(query) if _has_embeddings() else None
    if query_vec:
        import numpy as np
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT e.memory_id, 1 - (e.vector <=> $1) AS similarity
                FROM embeddings e
                JOIN memories m ON m.id = e.memory_id
                WHERE m.agent_name = $3
                ORDER BY e.vector <=> $1
                LIMIT $2
                """,
                np.array(query_vec, dtype=np.float32), max_results * 2, agent_name,
            )
            if rows:
                max_sim = max(r["similarity"] for r in rows) or 1.0
                vec_results = {r["memory_id"]: r["similarity"] / max_sim for r in rows if r["similarity"] > 0}

    if not bm25_results and not vec_results:
        return f"No matches for: {query}"

    # Merge scores
    if vec_results and bm25_results:
        merged = _merge_scores(bm25_results, vec_results, max_results)
        search_type = "hybrid"
    elif vec_results:
        merged = sorted(vec_results.items(), key=lambda x: -x[1])[:max_results]
        search_type = "vector"
    else:
        merged = sorted(bm25_results.items(), key=lambda x: -x[1])[:max_results]
        search_type = "bm25"

    ids = [mid for mid, _ in merged]
    if not ids:
        return f"No matches for: {query}"

    # Fetch full content
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, content, tags, created_at FROM memories WHERE id = ANY($1::bigint[])",
            ids,
        )
    row_map = {r["id"]: r for r in rows}

    lines = []
    for mid, score in merged:
        row = row_map.get(mid)
        if not row:
            continue
        tag_part = f" [{row['tags']}]" if row["tags"] else ""
        created = row["created_at"].strftime("%Y-%m-%d") if hasattr(row["created_at"], "strftime") else str(row["created_at"])[:10]
        lines.append(f"[#{mid} {created}{tag_part} score={score:.2f}] {row['content']}")

    log.info("memory search [pg] (%s) '%s' → %d result(s)", search_type, query, len(lines))
    return "\n".join(lines)


# ── Auto-flush: summarize conversation before context gets too long ───────────

FLUSH_PROMPT = (
    "The conversation is getting long. Before it gets truncated, save the most important "
    "information from this conversation to memory using memory_save. Focus on:\n"
    "- User preferences and corrections\n"
    "- Key decisions and outcomes\n"
    "- Facts that would be useful in future conversations\n"
    "Do NOT save trivial small talk. Be concise."
)

def should_flush(history: list[dict]) -> bool:
    """Check if conversation history is long enough to trigger auto-flush."""
    total_chars = sum(
        len(json.dumps(msg.get("content", ""), ensure_ascii=False))
        for msg in history
    )
    return total_chars >= FLUSH_THRESHOLD_CHARS


def get_flush_prompt() -> str:
    return FLUSH_PROMPT
