"""Migrate existing SQLite data to PostgreSQL.

Usage:
    DATABASE_URL=postgresql://... python scripts/migrate_to_postgres.py

Reads from local SQLite files:
  - workspace/memory/memory.db  (memories + embeddings)
  - workspace/sessions.db       (session messages)
  - workspace/cron.db           (cron jobs)

Writes to PostgreSQL via DATABASE_URL. Idempotent — safe to run multiple times.
"""

import asyncio
import os
import sqlite3
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _parse_ts(value: str | None) -> datetime | None:
    """Parse an ISO timestamp string from SQLite into a datetime for asyncpg."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


async def main():
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print("Error: DATABASE_URL environment variable is not set.")
        sys.exit(1)

    import ssl
    import asyncpg
    import numpy as np
    from pgvector.asyncpg import register_vector

    project_root = Path(__file__).parent.parent
    workspace = project_root / "workspace"

    memory_db_path = workspace / "memory" / "memory.db"
    sessions_db_path = workspace / "sessions.db"
    cron_db_path = workspace / "cron.db"

    ssl_ctx = ssl.create_default_context()

    async def _init_conn(conn):
        await register_vector(conn)

    print(f"Connecting to PostgreSQL...")
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3, ssl=ssl_ctx, init=_init_conn)

    # Ensure schema exists
    from bot.db import ensure_schema
    # Temporarily set the pool so ensure_schema can use it
    import bot.db as db_mod
    db_mod._pool = pool
    await ensure_schema()
    print("Schema verified.")

    total = {"memories": 0, "embeddings": 0, "messages": 0, "cron_jobs": 0, "health_logs": 0, "weight_goals": 0, "skipped": 0}

    # ── Migrate memories ──────────────────────────────────────────────────
    if memory_db_path.exists():
        print(f"\nMigrating memories from {memory_db_path}...")
        conn = sqlite3.connect(str(memory_db_path))
        conn.row_factory = sqlite3.Row

        rows = conn.execute("SELECT id, content, tags, source, created_at FROM memories").fetchall()
        print(f"  Found {len(rows)} memories")

        async with pool.acquire() as pg:
            for row in rows:
                try:
                    await pg.execute(
                        """INSERT INTO memories (id, content, tags, source, created_at)
                           VALUES ($1, $2, $3, $4, $5)
                           ON CONFLICT (id) DO NOTHING""",
                        row["id"], row["content"], row["tags"], row["source"],
                        _parse_ts(row["created_at"]),
                    )
                    total["memories"] += 1
                except Exception as e:
                    print(f"  Warning: skipping memory #{row['id']}: {e}")
                    total["skipped"] += 1

            # Reset sequence to max id
            max_id = await pg.fetchval("SELECT COALESCE(MAX(id), 0) FROM memories")
            if max_id > 0:
                await pg.execute(f"SELECT setval('memories_id_seq', {max_id})")

        # Migrate embeddings
        try:
            emb_rows = conn.execute("SELECT memory_id, vector FROM embeddings").fetchall()
            print(f"  Found {len(emb_rows)} embeddings")

            async with pool.acquire() as pg:
                for row in emb_rows:
                    try:
                        blob = row["vector"]
                        n = len(blob) // 4
                        vec = list(struct.unpack(f"{n}f", blob))
                        await pg.execute(
                            """INSERT INTO embeddings (memory_id, vector)
                               VALUES ($1, $2)
                               ON CONFLICT (memory_id) DO NOTHING""",
                            row["memory_id"], np.array(vec, dtype=np.float32),
                        )
                        total["embeddings"] += 1
                    except Exception as e:
                        print(f"  Warning: skipping embedding for memory #{row['memory_id']}: {e}")
                        total["skipped"] += 1
        except sqlite3.OperationalError:
            print("  No embeddings table found, skipping.")

        conn.close()
    else:
        print(f"\nNo memory database found at {memory_db_path}, skipping.")

    # ── Migrate session messages ──────────────────────────────────────────
    if sessions_db_path.exists():
        print(f"\nMigrating sessions from {sessions_db_path}...")
        conn = sqlite3.connect(str(sessions_db_path))
        conn.row_factory = sqlite3.Row

        rows = conn.execute("SELECT id, session_key, role, content, created_at FROM messages").fetchall()
        print(f"  Found {len(rows)} messages")

        async with pool.acquire() as pg:
            for row in rows:
                try:
                    await pg.execute(
                        """INSERT INTO messages (id, session_key, role, content, created_at)
                           VALUES ($1, $2, $3, $4, $5)
                           ON CONFLICT (id) DO NOTHING""",
                        row["id"], row["session_key"], row["role"], row["content"],
                        _parse_ts(row["created_at"]),
                    )
                    total["messages"] += 1
                except Exception as e:
                    print(f"  Warning: skipping message #{row['id']}: {e}")
                    total["skipped"] += 1

            # Reset sequence
            max_id = await pg.fetchval("SELECT COALESCE(MAX(id), 0) FROM messages")
            if max_id > 0:
                await pg.execute(f"SELECT setval('messages_id_seq', {max_id})")

        conn.close()
    else:
        print(f"\nNo sessions database found at {sessions_db_path}, skipping.")

    # ── Migrate cron jobs ─────────────────────────────────────────────────
    if cron_db_path.exists():
        print(f"\nMigrating cron jobs from {cron_db_path}...")
        conn = sqlite3.connect(str(cron_db_path))
        conn.row_factory = sqlite3.Row

        rows = conn.execute("SELECT * FROM cron_jobs").fetchall()
        print(f"  Found {len(rows)} cron jobs")

        async with pool.acquire() as pg:
            for row in rows:
                try:
                    await pg.execute(
                        """INSERT INTO cron_jobs
                           (id, name, schedule_type, schedule_value, timezone, payload,
                            channel_id, enabled, created_at, next_run_at, last_run_at,
                            last_status, last_error, consecutive_errors,
                            session_mode, context, model, delivery_channel)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                           ON CONFLICT (id) DO NOTHING""",
                        row["id"], row["name"], row["schedule_type"], row["schedule_value"],
                        row["timezone"], row["payload"], row["channel_id"],
                        bool(row["enabled"]), _parse_ts(row["created_at"]), row["next_run_at"],
                        row["last_run_at"], row["last_status"], row["last_error"],
                        row["consecutive_errors"],
                        row["session_mode"] if "session_mode" in row.keys() else "isolated",
                        row["context"] if "context" in row.keys() else "",
                        row["model"] if "model" in row.keys() else "",
                        row["delivery_channel"] if "delivery_channel" in row.keys() else "discord",
                    )
                    total["cron_jobs"] += 1
                except Exception as e:
                    print(f"  Warning: skipping cron job '{row['name']}': {e}")
                    total["skipped"] += 1

        conn.close()
    else:
        print(f"\nNo cron database found at {cron_db_path}, skipping.")

    # ── Migrate health data ──────────────────────────────────────────────
    health_db_path = workspace / "health.db"
    if health_db_path.exists():
        print(f"\nMigrating health data from {health_db_path}...")
        conn = sqlite3.connect(str(health_db_path))
        conn.row_factory = sqlite3.Row

        # Health logs
        try:
            rows = conn.execute("SELECT id, type, data, logged_at FROM health_logs").fetchall()
            print(f"  Found {len(rows)} health logs")

            async with pool.acquire() as pg:
                for row in rows:
                    try:
                        await pg.execute(
                            """INSERT INTO health_logs (id, type, data, logged_at)
                               VALUES ($1, $2, $3, $4)
                               ON CONFLICT (id) DO NOTHING""",
                            row["id"], row["type"], row["data"],
                            _parse_ts(row["logged_at"]),
                        )
                        total["health_logs"] += 1
                    except Exception as e:
                        print(f"  Warning: skipping health log #{row['id']}: {e}")
                        total["skipped"] += 1

                # Reset sequence
                max_id = await pg.fetchval("SELECT COALESCE(MAX(id), 0) FROM health_logs")
                if max_id > 0:
                    await pg.execute(f"SELECT setval('health_logs_id_seq', {max_id})")
        except sqlite3.OperationalError:
            print("  No health_logs table found, skipping.")

        # Weight goals
        try:
            rows = conn.execute(
                "SELECT id, start_weight, target_weight, start_date, target_date, created_at "
                "FROM weight_goals"
            ).fetchall()
            print(f"  Found {len(rows)} weight goals")

            async with pool.acquire() as pg:
                for row in rows:
                    try:
                        await pg.execute(
                            """INSERT INTO weight_goals (id, start_weight, target_weight, start_date, target_date, created_at)
                               VALUES ($1, $2, $3, $4, $5, $6)
                               ON CONFLICT (id) DO NOTHING""",
                            row["id"], row["start_weight"], row["target_weight"],
                            row["start_date"], row["target_date"],
                            _parse_ts(row["created_at"]),
                        )
                        total["weight_goals"] += 1
                    except Exception as e:
                        print(f"  Warning: skipping weight goal #{row['id']}: {e}")
                        total["skipped"] += 1

                # Reset sequence
                max_id = await pg.fetchval("SELECT COALESCE(MAX(id), 0) FROM weight_goals")
                if max_id > 0:
                    await pg.execute(f"SELECT setval('weight_goals_id_seq', {max_id})")
        except sqlite3.OperationalError:
            print("  No weight_goals table found, skipping.")

        conn.close()
    else:
        print(f"\nNo health database found at {health_db_path}, skipping.")

    await pool.close()

    print(f"\n{'='*50}")
    print(f"Migration complete!")
    print(f"  Memories:     {total['memories']}")
    print(f"  Embeddings:   {total['embeddings']}")
    print(f"  Messages:     {total['messages']}")
    print(f"  Cron jobs:    {total['cron_jobs']}")
    print(f"  Health logs:  {total['health_logs']}")
    print(f"  Weight goals: {total['weight_goals']}")
    if total["skipped"]:
        print(f"  Skipped:      {total['skipped']} (see warnings above)")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
