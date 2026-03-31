# Agent Database Management — Design Spec

## Summary

Migrate agent workspace (SOUL.md, IDENTITY.md, USER.md) and runtime config (config.yaml) from local files to PostgreSQL. Add a FastAPI management API and a React frontend for agent CRUD, document editing with version history.

## Context

Currently, MiniClaw runs as a single bot instance with personality defined by local files (`workspace/SOUL.md`, `IDENTITY.md`, etc.) and runtime config in `config.yaml`. This design moves all agent configuration to the database, enabling:

- Multiple independent agent instances managed from one DB
- Version-controlled document editing (soul, identity, user_doc) with rollback
- A web UI for creating and managing agents without touching files or code

Each agent is an independently deployed bot instance with its own Discord token, LLM config, and personality.

## Database Schema

PostgreSQL only (no SQLite fallback for agent management).

### `agents` table

```sql
CREATE TABLE agents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL UNIQUE,        -- machine identifier, e.g. "peter-griffin"
    display_name TEXT NOT NULL,               -- display name, e.g. "PeterGriffin"
    emoji        TEXT NOT NULL DEFAULT '',
    config       JSONB NOT NULL DEFAULT '{}', -- full runtime config (llm, discord, gateway, services)
    enabled      BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

The `config` JSONB field stores the equivalent of what is currently in `config.yaml`, per agent:

```json
{
  "llm": {
    "provider": "anthropic",
    "anthropic": { "model": "claude-sonnet-4-20250514" },
    "max_history": 50,
    "max_tokens": 4096,
    "tools_enabled": true
  },
  "discord": {
    "bot_token": "...",
    "greeting_channel_id": "...",
    "allowed_dm_users": [],
    "auto_reply": { "enabled": false },
    "stream": { "flush_interval": 0.1, "flush_chars": 50 }
  },
  "gateway": { ... },
  "services": { ... }
}
```

Note: `discord.bot_token` moves into the per-agent config JSONB. The global `.env` no longer contains `DISCORD_BOT_TOKEN`.

### `agent_documents` table

```sql
CREATE TABLE agent_documents (
    id         BIGSERIAL PRIMARY KEY,
    agent_id   UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    doc_type   TEXT NOT NULL,                 -- 'soul' | 'identity' | 'user_doc'
    content    TEXT NOT NULL DEFAULT '',
    version    INTEGER NOT NULL,              -- starts at 1, auto-incremented per (agent_id, doc_type)
    message    TEXT NOT NULL DEFAULT '',      -- optional version note
    created_by TEXT NOT NULL DEFAULT '',      -- who made the change
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (agent_id, doc_type, version)
);

CREATE INDEX idx_agent_docs_latest
    ON agent_documents (agent_id, doc_type, version DESC);
```

Usage patterns:
- **Latest version:** `WHERE agent_id = $1 AND doc_type = $2 ORDER BY version DESC LIMIT 1`
- **History:** same condition without LIMIT
- **Rollback:** insert a new version with content copied from the target version

## Bot Startup Flow

```
main.py
  |
  +-- Connect to PostgreSQL (DATABASE_URL from .env)
  +-- SELECT * FROM agents WHERE enabled = true
  +-- For each enabled agent:
  |     +-- Parse config JSONB -> AppConfig
  |     +-- Load latest soul, identity, user_doc from agent_documents
  |     +-- Build system prompt (same logic as current build_system_prompt)
  |     +-- Create Discord client with agent's bot_token
  |     +-- Start client
  +-- Run all clients concurrently (asyncio.gather)
```

### Remaining `.env` variables

Only global secrets that are not per-agent:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection (required) |
| `OPENAI_API_KEY` | Shared: embeddings, STT/TTS |
| `GITHUB_TOKEN` | Shared: exec tool |

Per-agent secrets (Discord token, Twilio, etc.) live in the agent's `config` JSONB.

### Remaining `config.yaml`

Minimal global config only:

```yaml
storage:
  backend: postgres  # always postgres for agent management
```

Or removed entirely if `DATABASE_URL` presence is sufficient to imply postgres.

## API Design (FastAPI)

Independent service at `web/api/`. Shares the same `DATABASE_URL`.

### Agent endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/agents` | List all agents (id, name, display_name, emoji, enabled) |
| POST | `/api/agents` | Create agent + initial document versions (v1) |
| GET | `/api/agents/:id` | Agent detail with latest document versions |
| PUT | `/api/agents/:id` | Update agent fields (name, display_name, emoji, config, enabled) |
| DELETE | `/api/agents/:id` | Delete agent (cascades to documents) |

### Document endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/agents/:id/documents/:doc_type` | Latest version |
| GET | `/api/agents/:id/documents/:doc_type/history` | Version history list |
| GET | `/api/agents/:id/documents/:doc_type/versions/:version` | Specific version |
| PUT | `/api/agents/:id/documents/:doc_type` | Create new version (body: `{content, message}`) |
| POST | `/api/agents/:id/documents/:doc_type/rollback` | Rollback (body: `{version}`) |

### Request/Response examples

**POST /api/agents**
```json
{
  "name": "peter-griffin",
  "display_name": "PeterGriffin",
  "emoji": "🍺",
  "config": { "llm": { "provider": "anthropic" }, "discord": { "bot_token": "..." } },
  "soul": "You're not a chatbot...",
  "identity": "Name: PeterGriffin\nEmoji: 🍺",
  "user_doc": ""
}
```

**PUT /api/agents/:id/documents/soul**
```json
{
  "content": "Updated soul content...",
  "message": "Made personality more casual"
}
```

## Frontend (Vite + React + TypeScript + Bun)

Located at `web/app/`, managed with bun.

### Pages

1. **Agent List** — cards or table showing all agents with status toggle, create button
2. **Agent Detail/Edit** — tabs for soul / identity / user_doc / config. Each document tab has a Markdown textarea + preview and version history panel

### Components

| Component | Purpose |
|-----------|---------|
| `AgentCard` | Agent summary in list view (name, emoji, enabled toggle) |
| `DocumentEditor` | Textarea + Markdown preview for soul/identity/user_doc |
| `VersionHistory` | Sidebar listing past versions with timestamps, diff view, rollback button |
| `ConfigEditor` | JSON editor for the agent's config JSONB |

### Tech stack

- **Bun** — package manager and dev server
- **Vite** — build tool
- **React 19** + TypeScript
- **shadcn/ui** + Tailwind CSS — UI components
- **React Router** — client-side routing

### Directory structure

```
web/
├── api/                        # FastAPI backend
│   ├── main.py                 # App, CORS, lifespan (asyncpg pool)
│   ├── routes/
│   │   ├── agents.py           # Agent CRUD
│   │   └── documents.py        # Document version CRUD
│   ├── models.py               # Pydantic request/response schemas
│   └── db.py                   # asyncpg helpers (connect, query)
│
└── app/                        # Vite + React frontend
    ├── src/
    │   ├── App.tsx
    │   ├── pages/
    │   │   ├── AgentList.tsx
    │   │   └── AgentDetail.tsx
    │   ├── components/
    │   │   ├── AgentCard.tsx
    │   │   ├── DocumentEditor.tsx
    │   │   ├── VersionHistory.tsx
    │   │   └── ConfigEditor.tsx
    │   └── lib/
    │       └── api.ts          # Fetch wrapper for /api/*
    ├── package.json
    ├── tsconfig.json
    ├── tailwind.config.ts
    └── vite.config.ts
```

## Migration Path

1. Add `agents` and `agent_documents` tables to PostgreSQL schema
2. Create a migration script that reads current `workspace/` files + `config.yaml` and inserts them as the first agent ("peter-griffin") with v1 documents
3. Modify `bot/config.py` to load agent config from DB instead of files when `DATABASE_URL` is set
4. Modify `main.py` to iterate enabled agents and start a Discord client per agent
5. Build FastAPI backend (`web/api/`)
6. Build React frontend (`web/app/`)

## What changes in existing code

| File | Change |
|------|--------|
| `bot/config.py` | `build_system_prompt()` reads from DB instead of files; `get_config()` loads per-agent config from DB |
| `bot/config_schema.py` | Add `discord.bot_token` field to `DiscordConfig` |
| `bot/storage/db.py` | Add `agents` + `agent_documents` table creation to `ensure_schema()` |
| `main.py` | Loop over enabled agents, create per-agent Discord client |
| `bot/client.py` | Accept agent-specific config + system prompt (no longer global singleton) |
| `bot/llm.py` | Accept per-agent provider/session config instead of global singleton |
| `.env` | Remove `DISCORD_BOT_TOKEN`; keep `DATABASE_URL`, `OPENAI_API_KEY`, `GITHUB_TOKEN` |
| `config.yaml` | Minimal or removed — global settings only |

## Testing

- Backend API: pytest + httpx async client against FastAPI test app with a test PostgreSQL DB
- Frontend: manual testing initially
- Migration script: test with current workspace files to verify round-trip

## Out of scope

- Auth/login for the web UI (can be added later)
- Real-time sync (bot auto-reloads when agent config changes in DB) — restart required for now
- WebSocket live preview of bot responses from the management UI
