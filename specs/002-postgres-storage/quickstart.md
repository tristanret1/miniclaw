# Quickstart: PostgreSQL Storage Migration

**Date**: 2026-03-24 | **Branch**: 002-postgres-storage

## Prerequisites

- Python 3.13+
- A Neon account (free tier): https://neon.tech
- Existing miniclaw deployment

## Setup Neon Database

1. Create a Neon project (free tier includes pgvector)
2. Enable pgvector extension: run `CREATE EXTENSION IF NOT EXISTS vector;` in SQL editor
3. Copy the **pooler** connection string (not the direct one)

## Configure

Add to `.env`:

```bash
DATABASE_URL=postgresql://user:pass@ep-xxx-pooler.us-east-1.neon.tech/miniclaw?sslmode=require
```

That's it. When `DATABASE_URL` is set, the bot uses PostgreSQL. When unset, it falls back to SQLite.

## Migrate Existing Data

If you have existing data in SQLite:

```bash
# From the project root
python scripts/migrate_to_postgres.py
```

The script reads from local SQLite files (`workspace/memory/memory.db`, `workspace/sessions.db`, `workspace/cron.db`) and writes to the PostgreSQL database configured in `DATABASE_URL`.

## Verify

```bash
# Start the bot
python main.py

# Check logs for:
# "Using PostgreSQL backend (Neon)" — confirms PG is active
# "Pool initialized (min=1, max=5)" — connection pool ready
```

## Local Development

No changes needed. Without `DATABASE_URL`, the bot uses SQLite as before:

```bash
# Just run without DATABASE_URL
python main.py
```

## New Dependencies

```
asyncpg>=0.30.0
pgvector>=0.3.0
```
