# Feature Specification: Migrate Storage to PostgreSQL

**Feature Branch**: `002-postgres-storage`
**Created**: 2026-03-24
**Status**: Draft
**Input**: User description: "目前的记忆管理 cron管理都是存在本地的sqlite中升级记忆存储在远端数据库中 使用Postgres来存储"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Memory persists across deploys and instances (Priority: P1)

As a bot operator, I want memory data (saved facts, user profiles, conversation highlights) stored in a remote PostgreSQL database so that data is not lost when the server is redeployed, restarted, or migrated to a different instance.

**Why this priority**: Memory is the bot's core intelligence — losing it means the bot forgets users, preferences, and accumulated knowledge. This is the highest-impact data to migrate.

**Independent Test**: Save a memory via the bot, redeploy or restart the service, then search for that memory — it should still be found.

**Acceptance Scenarios**:

1. **Given** a running bot with PostgreSQL configured, **When** the agent calls `memory_save` with content and tags, **Then** the memory is persisted in PostgreSQL and immediately searchable via `memory_search`.
2. **Given** memories stored in PostgreSQL, **When** the bot process restarts or is redeployed to a new instance, **Then** all previously saved memories are accessible without data loss.
3. **Given** a query submitted to `memory_search`, **When** full-text search executes, **Then** results are returned with equivalent relevance to the current implementation.
4. **Given** `OPENAI_API_KEY` is configured, **When** a memory is saved, **Then** its vector embedding is stored in PostgreSQL and used in hybrid search alongside full-text search.

---

### User Story 2 - Cron jobs persist across deploys (Priority: P2)

As a bot operator, I want cron job definitions (schedules, payloads, state) stored in PostgreSQL so that scheduled tasks survive server redeployments without manual re-creation.

**Why this priority**: Cron jobs define recurring tasks (reminders, health checks, etc.). Losing them on redeploy forces manual re-setup, which is error-prone and disrupts automated workflows.

**Independent Test**: Create a cron job via the bot, redeploy the service, then list jobs — the previously created job should still appear with correct schedule and state.

**Acceptance Scenarios**:

1. **Given** a running bot with PostgreSQL configured, **When** the agent creates a cron job, **Then** the job is persisted in PostgreSQL with all fields (schedule, payload, state, next_run_at).
2. **Given** cron jobs stored in PostgreSQL, **When** the scheduler ticks, **Then** due jobs are found and executed correctly, and state (last_run_at, next_run_at, consecutive_errors) is updated in PostgreSQL.
3. **Given** an existing cron job in PostgreSQL, **When** the bot restarts, **Then** the scheduler catches up missed runs and resumes normal scheduling.

---

### User Story 3 - Session history persists across deploys (Priority: P2)

As a bot user, I want my conversation history preserved when the bot is redeployed so that the bot remembers our recent conversation context.

**Why this priority**: Session history provides conversation continuity. Without it, every redeploy resets all conversations, degrading user experience.

**Independent Test**: Have a conversation with the bot, redeploy the service, then send a follow-up message — the bot should have context from the prior conversation.

**Acceptance Scenarios**:

1. **Given** a running bot with PostgreSQL configured, **When** messages are exchanged in a session, **Then** each message is persisted to PostgreSQL.
2. **Given** session history in PostgreSQL, **When** the bot restarts and a user sends a message, **Then** the bot loads recent history from PostgreSQL and responds with context.

---

### User Story 4 - Backward compatibility with SQLite (Priority: P3)

As a bot operator running a local/dev setup, I want the bot to fall back to SQLite when no PostgreSQL connection is configured, so that development and simple deployments remain zero-dependency.

**Why this priority**: Not all deployments need a remote database. Local development and single-machine setups should continue working with zero additional infrastructure.

**Independent Test**: Start the bot without any `DATABASE_URL` configured — it should start normally using SQLite, with no errors or warnings beyond an info-level log.

**Acceptance Scenarios**:

1. **Given** no `DATABASE_URL` environment variable set, **When** the bot starts, **Then** it uses SQLite for all storage (current behavior unchanged).
2. **Given** `DATABASE_URL` is set to a PostgreSQL connection string, **When** the bot starts, **Then** it uses PostgreSQL for all storage.

---

### User Story 5 - One-time migration from SQLite to PostgreSQL (Priority: P3)

As a bot operator migrating to PostgreSQL, I want a migration tool to copy existing SQLite data (memories, cron jobs, sessions) into PostgreSQL so that I don't lose accumulated data.

**Why this priority**: Existing deployments have valuable data in SQLite. A migration path prevents data loss during the transition.

**Independent Test**: Run the migration script against a SQLite database with known data, then verify all records appear correctly in PostgreSQL.

**Acceptance Scenarios**:

1. **Given** existing SQLite databases with memories, cron jobs, and sessions, **When** the migration script is run, **Then** all records are copied to PostgreSQL with correct data and timestamps.
2. **Given** the migration has already been run, **When** the migration script is run again, **Then** it skips duplicates or reports that migration is already complete (idempotent).

---

### Edge Cases

- What happens when PostgreSQL is temporarily unreachable during a save operation? The system should retry or fail gracefully with an error message, not crash.
- What happens when the database schema is outdated? The system should auto-create tables on startup.
- What happens when full-text search queries contain special characters that differ between SQLite FTS5 and PostgreSQL tsvector? The search layer should handle syntax normalization.
- What happens when the migration script encounters corrupt or incomplete SQLite data? It should skip invalid records with warnings, not abort entirely.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support PostgreSQL as a storage backend for memories, cron jobs, and session history when `DATABASE_URL` is configured.
- **FR-002**: System MUST fall back to SQLite when no `DATABASE_URL` is set (zero-config local development).
- **FR-003**: System MUST provide full-text search for memories in PostgreSQL with equivalent relevance to the current BM25/FTS5 implementation.
- **FR-004**: System MUST store and retrieve vector embeddings in PostgreSQL for hybrid memory search.
- **FR-005**: System MUST auto-create database tables on first connection (no manual DDL required).
- **FR-006**: System MUST provide a migration script to copy existing SQLite data to PostgreSQL.
- **FR-007**: System MUST handle PostgreSQL connection failures gracefully (log errors, surface to user, no crashes).
- **FR-008**: System MUST use connection pooling for PostgreSQL to handle concurrent operations efficiently.
- **FR-009**: The migration script MUST be idempotent — safe to run multiple times without duplicating data.

### Key Entities

- **Memory**: A saved fact or observation (content, tags, source, created_at) with optional vector embedding. Supports full-text search and hybrid retrieval.
- **Cron Job**: A scheduled task definition (name, schedule, payload, channel, state) with execution tracking (last_run, next_run, errors).
- **Session Message**: A conversation turn (session_key, role, content, created_at) grouped by session for history retrieval.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing bot features (memory save/search, cron create/list/delete, session history) work identically whether backed by SQLite or PostgreSQL — no user-visible behavior change.
- **SC-002**: Memory search returns relevant results within 2 seconds for a database with up to 10,000 memories.
- **SC-003**: Data survives a full server redeploy: memories, cron jobs, and recent session history are all intact after restarting the bot on a fresh instance.
- **SC-004**: The bot starts successfully with zero configuration changes when no `DATABASE_URL` is set (backward compatibility).
- **SC-005**: Migration script transfers all existing data from SQLite to PostgreSQL in under 5 minutes for databases up to 100,000 records.
- **SC-006**: All existing tests continue to pass without modification (SQLite remains the test backend).
