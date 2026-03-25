# Data Model: Migrate Storage to PostgreSQL

**Date**: 2026-03-24 | **Branch**: 002-postgres-storage

## Overview

Three SQLite databases converge into a single PostgreSQL database with four tables. The schema preserves all existing fields and adds PostgreSQL-native full-text search and vector indexing.

## Entities

### memories

Stores agent-saved facts, user profiles, and conversation highlights.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | BIGSERIAL | PRIMARY KEY | Auto-increment |
| content | TEXT | NOT NULL | The memory text |
| tags | TEXT | nullable | Comma-separated tags |
| source | TEXT | nullable | "agent", "system", etc. |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | ISO timestamp |
| content_tsv | tsvector | GENERATED STORED | Auto-computed FTS column |

**Indexes**:
- `idx_memories_fts` — GIN index on `content_tsv` for full-text search
- Primary key index on `id`

**Generated column**:
```
content_tsv = setweight(to_tsvector('english', content), 'A') ||
              setweight(to_tsvector('english', COALESCE(tags, '')), 'B')
```

### embeddings

Vector embeddings for hybrid memory search (pgvector).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| memory_id | BIGINT | PRIMARY KEY, FK → memories(id) ON DELETE CASCADE | 1:1 with memories |
| vector | vector(1536) | NOT NULL | text-embedding-3-small output |

**Indexes**:
- `idx_embeddings_vector` — HNSW index on `vector` using `vector_cosine_ops`

### cron_jobs

Scheduled task definitions and execution state.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | TEXT | PRIMARY KEY | UUID hex (12 chars) |
| name | TEXT | NOT NULL | Human-readable name |
| schedule_type | TEXT | NOT NULL | "every", "cron", "at" |
| schedule_value | TEXT | NOT NULL | Duration or cron expression |
| timezone | TEXT | NOT NULL DEFAULT 'America/Vancouver' | IANA timezone |
| payload | TEXT | NOT NULL | Prompt text for LLM |
| channel_id | TEXT | NOT NULL | Discord channel or phone number |
| enabled | BOOLEAN | NOT NULL DEFAULT true | Active flag |
| created_at | TIMESTAMPTZ | NOT NULL | Creation timestamp |
| next_run_at | DOUBLE PRECISION | NOT NULL | Unix timestamp |
| last_run_at | DOUBLE PRECISION | nullable | Unix timestamp |
| last_status | TEXT | nullable | "ok" or "error" |
| last_error | TEXT | nullable | Error message (truncated) |
| consecutive_errors | INTEGER | NOT NULL DEFAULT 0 | For backoff |
| session_mode | TEXT | NOT NULL DEFAULT 'isolated' | "isolated" or "persistent" |
| context | TEXT | NOT NULL DEFAULT '' | Extra system instructions |
| model | TEXT | NOT NULL DEFAULT '' | Model override |
| delivery_channel | TEXT | NOT NULL DEFAULT 'discord' | "discord", "sms", "imessage" |

**Indexes**:
- Primary key on `id`
- `idx_cron_next_run` on `(enabled, next_run_at)` for scheduler tick queries

### messages

Conversation session history.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | BIGSERIAL | PRIMARY KEY | Auto-increment |
| session_key | TEXT | NOT NULL | "{channel_id}:{user_id}" |
| role | TEXT | NOT NULL | "user" or "assistant" |
| content | TEXT | NOT NULL | JSON string or plain text |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() | Timestamp |

**Indexes**:
- `idx_messages_session` on `(session_key, id)` for history retrieval

## Relationships

```
memories 1──1 embeddings  (optional: only when OPENAI_API_KEY set)
```

All other tables are independent (no foreign keys between them).

## State Transitions

### cron_jobs lifecycle

```
created (enabled=true)
  → executing (no DB state change, in-memory only)
    → success: last_status='ok', consecutive_errors=0, next_run_at updated
    → failure: last_status='error', consecutive_errors++, backoff applied
  → disabled (enabled=false): one-shot "at" jobs after execution, or manual disable
```

## Scale Assumptions

- Memories: < 10,000 records (personal bot)
- Cron jobs: < 50 active jobs
- Session messages: < 100,000 records (trimmed by MAX_HISTORY)
- Embeddings: 1:1 with memories when OPENAI_API_KEY is set
- Vector dimension: 1536 (text-embedding-3-small, fixed)
