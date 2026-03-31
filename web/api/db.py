"""asyncpg pool management for the FastAPI service."""

from __future__ import annotations

import os
import ssl

_pool = None  # asyncpg.Pool | None


async def get_pool():
    """Return the asyncpg connection pool, creating it on first call.

    Uses DATABASE_URL env var. SSL is always enabled (required for Neon).
    Raises RuntimeError if DATABASE_URL is not set.
    """
    global _pool
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    if _pool is not None:
        return _pool

    import asyncpg

    ssl_ctx = ssl.create_default_context()

    _pool = await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=5,
        ssl=ssl_ctx,
    )
    return _pool


async def close_pool() -> None:
    """Close the connection pool gracefully."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
