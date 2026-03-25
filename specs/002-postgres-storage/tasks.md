# Tasks: Migrate Storage to PostgreSQL

**Input**: Design documents from `/specs/002-postgres-storage/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Not explicitly requested in spec — test tasks omitted. Existing tests must continue passing (SC-006).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add dependencies and create the database backend factory module

- [x] T001 Add `asyncpg>=0.30.0` and `pgvector>=0.3.0` to `requirements.txt`
- [x] T002 Add `DATABASE_URL` env var to `bot/config.py` and document in `.env.example`
- [x] T003 Create database backend factory module `bot/db.py` with `get_pool()`, `use_postgres()`, `close_pool()`, and pool lifecycle management (min=1, max=5, SSL required)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema auto-creation and pgvector type registration — MUST complete before any user story

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Implement PostgreSQL schema auto-creation in `bot/db.py`: `ensure_schema()` that creates all four tables (memories, embeddings, cron_jobs, messages) with indexes, tsvector generated column, and `CREATE EXTENSION IF NOT EXISTS vector` on first connection
- [x] T005 Register pgvector custom type codec with asyncpg in `bot/db.py` pool setup (using `pgvector.asyncpg.register_vector`)
- [x] T006 Add startup hook in `main.py` to call `db.get_pool()` + `db.ensure_schema()` on bot ready (warm up pool), with info-level log: "Using PostgreSQL backend (Neon)" or "Using SQLite backend (local)"

**Checkpoint**: Pool initializes, schema auto-creates, bot starts with either backend logged

---

## Phase 3: User Story 1 — Memory persists across deploys (Priority: P1) MVP

**Goal**: Memory save/search works against PostgreSQL with full-text search (tsvector) and hybrid vector search (pgvector)

**Independent Test**: Save a memory via the bot, restart the process, search for it — result found

### Implementation for User Story 1

- [x] T007 [US1] Add PostgreSQL `save()` code path in `bot/memory.py`: INSERT into `memories` table via asyncpg, return new ID. Gate behind `db.use_postgres()`
- [x] T008 [US1] Add PostgreSQL vector embedding storage in `bot/memory.py`: INSERT into `embeddings` table with pgvector vector type (reuse existing OpenAI embedding call). Gate behind `db.use_postgres()` and `OPENAI_API_KEY`
- [x] T009 [US1] Add PostgreSQL full-text search in `bot/memory.py`: query using `ts_rank_cd()` + `plainto_tsquery()` against `content_tsv` column, normalize scores to 0..1. Gate behind `db.use_postgres()`
- [x] T010 [US1] Add PostgreSQL vector search in `bot/memory.py`: query using `<=>` cosine distance operator with HNSW index, normalize scores to 0..1. Gate behind `db.use_postgres()` and `OPENAI_API_KEY`
- [x] T011 [US1] Add PostgreSQL hybrid search merge in `bot/memory.py`: weighted merge (BM25=0.4, vector=0.6) matching existing logic, return formatted results. Gate behind `db.use_postgres()`
- [x] T012 [US1] Preserve daily Markdown log append in `bot/memory.py` — this is file-based and should work regardless of database backend

**Checkpoint**: `memory_save` and `memory_search` tools work end-to-end against PostgreSQL

---

## Phase 4: User Story 2 — Cron jobs persist across deploys (Priority: P2)

**Goal**: Cron job CRUD and scheduler execution work against PostgreSQL

**Independent Test**: Create a cron job, restart the bot, list jobs — previously created job appears with correct state

### Implementation for User Story 2

- [x] T013 [US2] Add PostgreSQL `create_job()` code path in `bot/cron.py`: INSERT into `cron_jobs` table via asyncpg. Gate behind `db.use_postgres()`
- [x] T014 [US2] Add PostgreSQL `list_jobs()` and `delete_job()` code paths in `bot/cron.py`: SELECT/DELETE against `cron_jobs` table. Gate behind `db.use_postgres()`
- [x] T015 [US2] Add PostgreSQL scheduler tick in `bot/cron.py`: `_on_tick()` queries due jobs via `SELECT ... WHERE enabled=true AND next_run_at <= $1`, updates state (`last_run_at`, `next_run_at`, `last_status`, `consecutive_errors`) after execution. Gate behind `db.use_postgres()`
- [x] T016 [US2] Add PostgreSQL `_apply_result()` in `bot/cron.py`: UPDATE job state after execution (success/failure), handle one-shot "at" job disabling. Gate behind `db.use_postgres()`

**Checkpoint**: `cron_create`, `cron_list`, `cron_delete` tools and scheduler tick work end-to-end against PostgreSQL

---

## Phase 5: User Story 3 — Session history persists across deploys (Priority: P2)

**Goal**: Session message persistence and retrieval work against PostgreSQL

**Independent Test**: Have a conversation, restart the bot, send a follow-up — bot has prior context

### Implementation for User Story 3

- [x] T017 [US3] Add PostgreSQL `_persist()` code path in `bot/session.py`: INSERT into `messages` table via asyncpg. Gate behind `db.use_postgres()`
- [x] T018 [US3] Add PostgreSQL `get_history()` code path in `bot/session.py`: SELECT recent messages (limit MAX_HISTORY*2) ordered by id, deserialize content JSON. Gate behind `db.use_postgres()`
- [x] T019 [US3] Add PostgreSQL `clear_session()` code path in `bot/session.py`: DELETE by session_key. Gate behind `db.use_postgres()`

**Checkpoint**: Conversation history loads from PostgreSQL after restart, trim and sanitize work as before

---

## Phase 6: User Story 4 — Backward compatibility with SQLite (Priority: P3)

**Goal**: Bot works identically when `DATABASE_URL` is not set — zero behavioral change

**Independent Test**: Start bot without `DATABASE_URL` — all features work, no errors, info log says "Using SQLite backend (local)"

### Implementation for User Story 4

- [x] T020 [US4] Verify all `db.use_postgres()` gates in `bot/memory.py`, `bot/session.py`, `bot/cron.py` fall through to existing SQLite code paths when `DATABASE_URL` is unset
- [x] T021 [US4] Run full existing test suite (`pytest`) with no `DATABASE_URL` set — all tests must pass without modification (SC-006)

**Checkpoint**: Existing SQLite behavior completely unchanged

---

## Phase 7: User Story 5 — One-time migration from SQLite to PostgreSQL (Priority: P3)

**Goal**: Migration script copies all existing SQLite data to PostgreSQL safely and idempotently

**Independent Test**: Run script against SQLite with known data, verify all records in PostgreSQL

### Implementation for User Story 5

- [x] T022 [US5] Create migration script `scripts/migrate_to_postgres.py`: read from SQLite files (`workspace/memory/memory.db`, `workspace/sessions.db`, `workspace/cron.db`), write to PostgreSQL via asyncpg using `DATABASE_URL`
- [x] T023 [US5] Implement idempotent migration logic in `scripts/migrate_to_postgres.py`: skip duplicates using `ON CONFLICT DO NOTHING` or pre-check, handle corrupt/incomplete SQLite records with warnings (not abort)
- [x] T024 [US5] Migrate vector embeddings in `scripts/migrate_to_postgres.py`: read BLOB embeddings from SQLite, convert to pgvector format, INSERT into `embeddings` table

**Checkpoint**: Full data migration works, script is safe to re-run

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Error handling, graceful degradation, and documentation

- [x] T025 [P] Add connection error handling in `bot/db.py`: retry logic for Neon cold starts, graceful failure with logged errors (FR-007), no crashes
- [x] T026 [P] Add pool cleanup in `main.py` or `bot/db.py`: call `close_pool()` on bot shutdown to release connections cleanly
- [x] T027 [P] Update `.env.example` with `DATABASE_URL` example and comment explaining SQLite fallback
- [x] T028 [P] Update `CLAUDE.md` project structure section to reflect new `bot/db.py` and `scripts/migrate_to_postgres.py`
- [ ] T029 (requires live Neon database) Run quickstart.md validation: follow setup steps end-to-end on a fresh Neon database

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **US1 Memory (Phase 3)**: Depends on Phase 2 — can start immediately after
- **US2 Cron (Phase 4)**: Depends on Phase 2 — can run in parallel with US1
- **US3 Sessions (Phase 5)**: Depends on Phase 2 — can run in parallel with US1/US2
- **US4 SQLite compat (Phase 6)**: Depends on US1+US2+US3 (verifies all gates work)
- **US5 Migration (Phase 7)**: Depends on Phase 2 (needs schema) — can run in parallel with US1-US3
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Independence

```
Phase 2 (Foundation) ──┬──► Phase 3 (US1: Memory)    ──┐
                       ├──► Phase 4 (US2: Cron)       ──┼──► Phase 6 (US4: SQLite compat)
                       ├──► Phase 5 (US3: Sessions)   ──┘         │
                       └──► Phase 7 (US5: Migration)              ▼
                                                           Phase 8 (Polish)
```

### Within Each User Story

- Core CRUD operations before search/query operations
- Gate (`use_postgres()`) added to every function that touches the database
- Existing SQLite code remains untouched — new code paths are additive

### Parallel Opportunities

- **Phase 1**: T001 and T002 can run in parallel (different files)
- **Phase 3-5**: US1, US2, US3 can all run in parallel after Phase 2
- **Phase 7**: Migration script can be developed in parallel with US1-US3
- **Phase 8**: All polish tasks marked [P] can run in parallel

---

## Parallel Example: After Phase 2 Completes

```bash
# Launch all three user stories in parallel:
Task: "US1 — PostgreSQL save() in bot/memory.py"
Task: "US2 — PostgreSQL create_job() in bot/cron.py"
Task: "US3 — PostgreSQL _persist() in bot/session.py"

# Launch migration script in parallel with implementation:
Task: "US5 — Create migration script in scripts/migrate_to_postgres.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T006)
3. Complete Phase 3: US1 Memory (T007-T012)
4. **STOP and VALIDATE**: Save a memory, restart bot, search — found?
5. Deploy if ready — memory persistence is the highest-value increment

### Incremental Delivery

1. Setup + Foundational → Pool + schema ready
2. Add US1 (Memory) → Test independently → Deploy (MVP!)
3. Add US2 (Cron) → Test independently → Deploy
4. Add US3 (Sessions) → Test independently → Deploy
5. Add US4 (SQLite verify) + US5 (Migration) → Full feature complete
6. Polish → Production ready

---

## Notes

- All PostgreSQL code paths gated behind `db.use_postgres()` — SQLite code untouched
- asyncpg uses `$1, $2` parameter placeholders (not `?` like SQLite)
- pgvector requires type registration on each new connection (handle in pool `init` callback)
- Neon pooler endpoint requires SSL (`sslmode=require`)
- Daily Markdown memory logs are file-based — unaffected by database backend choice
