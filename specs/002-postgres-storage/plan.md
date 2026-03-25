# Implementation Plan: Migrate Storage to PostgreSQL

**Branch**: `002-postgres-storage` | **Date**: 2026-03-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-postgres-storage/spec.md`

## Summary

Migrate miniclaw's three SQLite-backed storage modules (memory, cron, sessions) to PostgreSQL on Neon serverless, using asyncpg for async operations, pgvector for indexed vector search, and PostgreSQL tsvector for full-text search. SQLite remains as a zero-config fallback when `DATABASE_URL` is not set.

## Technical Context

**Language/Version**: Python 3.13+
**Primary Dependencies**: discord.py, httpx, asyncpg (new), pgvector-python (new)
**Storage**: PostgreSQL 16 (Neon serverless) with pgvector extension; SQLite fallback
**Testing**: pytest + pytest-asyncio (auto mode)
**Target Platform**: Linux server (Ubuntu on EC2)
**Project Type**: Discord chatbot (asyncio-based)
**Performance Goals**: Memory search < 2s for 10k records
**Constraints**: Neon free tier (3GB storage, ~100 connections); bot runs as single process
**Scale/Scope**: < 10k memories, < 50 cron jobs, < 100k session messages

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution is a blank template — no project-specific gates defined. **PASS.**

Post-design re-check: No new violations. The design adds 2 dependencies (asyncpg, pgvector) and 1 new module (bot/db.py). All changes are additive — existing SQLite code paths remain untouched. **PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/002-postgres-storage/
├── plan.md              # This file
├── research.md          # Phase 0: technology decisions
├── data-model.md        # Phase 1: PostgreSQL schema
├── quickstart.md        # Phase 1: setup guide
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
bot/
├── db.py                # NEW: Database backend factory + pool management
├── memory.py            # MODIFIED: add PostgreSQL code path
├── session.py           # MODIFIED: add PostgreSQL code path
├── cron.py              # MODIFIED: add PostgreSQL code path
├── config.py            # MODIFIED: add DATABASE_URL
└── ...                  # Unchanged modules

scripts/
└── migrate_to_postgres.py  # NEW: SQLite → PostgreSQL migration

tests/
├── test_db.py           # NEW: pool init, backend selection
├── test_memory.py       # MODIFIED: add PostgreSQL-path tests
├── test_session.py      # MODIFIED: add PostgreSQL-path tests
└── test_cron.py         # MODIFIED: add PostgreSQL-path tests
```

**Structure Decision**: Single-project layout (existing). New code goes into the existing `bot/` and `scripts/` directories. One new module (`bot/db.py`) acts as the database factory. No new packages or structural changes.

## Complexity Tracking

No constitution violations to justify.
