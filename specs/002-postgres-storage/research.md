# Research: Migrate Storage to PostgreSQL

**Date**: 2026-03-24 | **Branch**: 002-postgres-storage

## R1: Async PostgreSQL Driver

**Decision**: asyncpg

**Rationale**: Best performance for raw SQL, built-in connection pooling via `asyncpg.create_pool()`, native pgvector support, and matches the codebase's 100% asyncio architecture (processor, client, cron scheduler). No ORM needed — the codebase already uses raw SQL everywhere.

**Alternatives considered**:
- psycopg3 (async mode): Viable but slightly more overhead, more ORM-oriented patterns. asyncpg is simpler for raw SQL.
- SQLAlchemy async: Over-engineered for this project's needs. Adds unnecessary abstraction.

## R2: Vector Embedding Storage (pgvector)

**Decision**: pgvector extension with `vector` column type, using cosine distance operator `<=>` for similarity search.

**Rationale**: pgvector provides native indexed vector search (IVFFlat/HNSW), eliminating the current brute-force cosine similarity scan over all embeddings. Available on Neon free tier out of the box. The `pgvector` Python package (`pgvector-python`) provides asyncpg type registration.

**Alternatives considered**:
- Raw BYTEA blobs (current approach in SQLite): No indexing, O(n) scan. Doesn't scale past a few thousand memories.
- Pinecone/Weaviate external vector DB: Overkill for a personal bot. Adds external dependency.

**Schema**:
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embeddings (
    memory_id BIGINT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
    vector vector(1536) NOT NULL  -- text-embedding-3-small dimension
);

CREATE INDEX idx_embeddings_vector ON embeddings USING hnsw (vector vector_cosine_ops);
```

## R3: Full-Text Search (SQLite FTS5 → PostgreSQL tsvector)

**Decision**: PostgreSQL `tsvector` generated column + `ts_rank_cd()` for BM25-like scoring.

**Rationale**: PostgreSQL's built-in FTS is mature, supports stemming, and `ts_rank_cd()` provides cover density ranking (similar to BM25). A generated `tsvector` column with GIN index gives equivalent or better performance than FTS5.

**Key differences from FTS5**:
- Query syntax: `plainto_tsquery()` for safe parsing (handles special chars automatically)
- Ranking: `ts_rank_cd()` instead of FTS5 `rank` (both normalize lower=better → higher=better)
- Fallback: `phraseto_tsquery()` or `websearch_to_tsquery()` for advanced queries
- Stemming: Built-in English stemmer (same as FTS5 `unicode61`)

**Schema**:
```sql
ALTER TABLE memories ADD COLUMN content_tsv tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', content), 'A') ||
        setweight(to_tsvector('english', COALESCE(tags, '')), 'B')
    ) STORED;

CREATE INDEX idx_memories_fts ON memories USING GIN(content_tsv);
```

## R4: Neon Serverless Considerations

**Decision**: Use Neon pooler endpoint with conservative pool settings.

**Rationale**: Neon free tier provides pgvector, 3GB storage, and connection pooling endpoint. The pooler endpoint handles cold starts transparently.

**Configuration**:
- Use `-pooler` connection string (not direct)
- Pool settings: `min_size=1, max_size=5` (Neon free tier allows ~100 connections)
- SSL required (`sslmode=require`)
- Warm up pool on bot startup to avoid first-request latency

**Alternatives considered**:
- Supabase: Also free tier with pgvector, but Neon's serverless model is simpler for a single-bot deployment
- Self-hosted on EC2: More control but adds ops burden (backups, updates, monitoring)
- AWS RDS: Paid, overkill for personal project

## R5: Dual-Backend Pattern (SQLite Fallback)

**Decision**: Conditional imports with factory function in a new `bot/db.py` module.

**Rationale**: The codebase is small (3 storage modules). A thin factory that returns either sync SQLite helpers or an async PostgreSQL pool is the minimal change. No abstract base classes or interface patterns needed — just `if DATABASE_URL:` branching at the module level. Existing sync SQLite code stays as-is; PostgreSQL code paths are async.

**Pattern**:
```python
# bot/db.py
DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool | None:
    """Return PostgreSQL pool if DATABASE_URL is set, else None."""
    ...

def use_postgres() -> bool:
    return bool(DATABASE_URL)
```

Each module (memory.py, session.py, cron.py) checks `use_postgres()` and delegates to the appropriate code path.

**Alternatives considered**:
- Abstract base class per module: Too much ceremony for 3 small modules
- Full ORM (SQLAlchemy): Adds dependency and complexity without benefit
- Environment-based import switching: Fragile, hard to test
