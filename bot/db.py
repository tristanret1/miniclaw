"""Database backend factory — PostgreSQL (asyncpg) with SQLite fallback."""

from __future__ import annotations

import asyncio
import ssl

from bot.config import DATABASE_URL
from bot.logger import get_logger

log = get_logger("db")

_pool = None  # asyncpg.Pool | None

_CONNECT_RETRIES = 3
_CONNECT_RETRY_DELAY = 2.0  # seconds


def use_postgres() -> bool:
    """Return True if PostgreSQL backend is configured."""
    return bool(DATABASE_URL)


async def get_pool():
    """Return the asyncpg connection pool, creating it on first call.

    Retries on connection failure (Neon cold starts may take a few seconds).
    Returns None if DATABASE_URL is not set.
    """
    global _pool
    if not DATABASE_URL:
        return None
    if _pool is not None:
        return _pool

    import asyncpg
    from pgvector.asyncpg import register_vector

    # Neon requires SSL
    ssl_ctx = ssl.create_default_context()

    async def _init_conn(conn):
        """Register pgvector type on each new connection."""
        await register_vector(conn)

    last_error = None
    for attempt in range(1, _CONNECT_RETRIES + 1):
        try:
            # First ensure pgvector extension exists (before pool init tries to register the type)
            conn = await asyncpg.connect(DATABASE_URL, ssl=ssl_ctx)
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            finally:
                await conn.close()

            _pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=5,
                ssl=ssl_ctx,
                init=_init_conn,
            )
            log.info("PostgreSQL pool initialized (min=1, max=5)")
            return _pool
        except (OSError, asyncpg.PostgresError, ValueError) as e:
            last_error = e
            if attempt < _CONNECT_RETRIES:
                log.warning("PostgreSQL connection attempt %d/%d failed: %s (retrying in %.0fs)",
                            attempt, _CONNECT_RETRIES, e, _CONNECT_RETRY_DELAY)
                await asyncio.sleep(_CONNECT_RETRY_DELAY)
            else:
                log.error("PostgreSQL connection failed after %d attempts: %s", _CONNECT_RETRIES, e)
                raise


async def ensure_schema() -> None:
    """Create tables and extensions if they don't exist."""
    pool = await get_pool()
    if pool is None:
        return

    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id BIGSERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                tags TEXT,
                source TEXT,
                agent_name TEXT NOT NULL DEFAULT 'default',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        # Add agent_name column if upgrading from older schema
        agent_col_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'memories' AND column_name = 'agent_name'
            )
        """)
        if not agent_col_exists:
            await conn.execute("""
                ALTER TABLE memories ADD COLUMN agent_name TEXT NOT NULL DEFAULT 'default'
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_agent
                ON memories (agent_name)
            """)

        # Add tsvector generated column if it doesn't exist
        col_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'memories' AND column_name = 'content_tsv'
            )
        """)
        if not col_exists:
            await conn.execute("""
                ALTER TABLE memories ADD COLUMN content_tsv tsvector
                GENERATED ALWAYS AS (
                    setweight(to_tsvector('english', content), 'A') ||
                    setweight(to_tsvector('english', COALESCE(tags, '')), 'B')
                ) STORED
            """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_fts
            ON memories USING GIN(content_tsv)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                memory_id BIGINT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
                vector vector(1536) NOT NULL
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_vector
            ON embeddings USING hnsw (vector vector_cosine_ops)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cron_jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                schedule_type TEXT NOT NULL,
                schedule_value TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'America/Vancouver',
                payload TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL,
                next_run_at DOUBLE PRECISION NOT NULL,
                last_run_at DOUBLE PRECISION,
                last_status TEXT,
                last_error TEXT,
                consecutive_errors INTEGER NOT NULL DEFAULT 0,
                session_mode TEXT NOT NULL DEFAULT 'isolated',
                context TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                delivery_channel TEXT NOT NULL DEFAULT 'discord'
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cron_next_run
            ON cron_jobs (enabled, next_run_at)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS health_logs (
                id BIGSERIAL PRIMARY KEY,
                type TEXT NOT NULL,
                data TEXT NOT NULL,
                logged_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_type_date
            ON health_logs (type, logged_at)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS weight_goals (
                id BIGSERIAL PRIMARY KEY,
                start_weight DOUBLE PRECISION NOT NULL,
                target_weight DOUBLE PRECISION NOT NULL,
                start_date TEXT NOT NULL,
                target_date TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id BIGSERIAL PRIMARY KEY,
                session_key TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages (session_key, id)
        """)

    log.info("PostgreSQL schema verified")


async def close_pool() -> None:
    """Close the connection pool gracefully."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        log.info("PostgreSQL pool closed")
