# Agent Database Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate agent configuration from local files/JSON to PostgreSQL, add a FastAPI management API, and build a React frontend for agent CRUD with document version history.

**Architecture:** Two new PostgreSQL tables (`agents`, `agent_documents`) store agent config and versioned personality docs. A standalone FastAPI service (`web/api/`) exposes CRUD endpoints. A Vite+React frontend (`web/app/`) provides the management UI. The bot's `load_agents()` gains a new DB-first loading path.

**Tech Stack:** Python 3.13+, asyncpg, FastAPI, Pydantic v2, React 19, TypeScript, Vite, Bun, shadcn/ui, Tailwind CSS.

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `web/api/main.py` | FastAPI app, CORS, lifespan (asyncpg pool init/close) |
| `web/api/db.py` | asyncpg pool management, query helpers |
| `web/api/models.py` | Pydantic request/response schemas |
| `web/api/routes/agents.py` | Agent CRUD endpoints |
| `web/api/routes/documents.py` | Document version CRUD endpoints |
| `web/api/routes/__init__.py` | Router aggregation |
| `web/app/src/App.tsx` | React app root with routing |
| `web/app/src/pages/AgentList.tsx` | Agent list page |
| `web/app/src/pages/AgentDetail.tsx` | Agent detail/edit page with doc tabs |
| `web/app/src/components/AgentCard.tsx` | Agent card for list view |
| `web/app/src/components/DocumentEditor.tsx` | Markdown textarea + preview |
| `web/app/src/components/VersionHistory.tsx` | Version history sidebar |
| `web/app/src/components/ConfigEditor.tsx` | JSON config editor |
| `web/app/src/lib/api.ts` | Fetch wrapper for API calls |
| `tests/web/test_agents_api.py` | API integration tests for agent endpoints |
| `tests/web/test_documents_api.py` | API integration tests for document endpoints |

### Modified files

| File | Change |
|------|--------|
| `bot/storage/db.py` | Add `agents` + `agent_documents` tables to `ensure_schema()` |
| `bot/agent.py` | Add `_load_from_db()` as highest-priority loader in `load_agents()` |
| `pyproject.toml` | Add `fastapi`, `uvicorn` to dependencies |

---

## Task 1: Add DB schema for agents and agent_documents

**Files:**
- Modify: `bot/storage/db.py:77-214` (add tables inside `ensure_schema()`)
- Test: `tests/web/test_agents_api.py` (schema creation test)

- [ ] **Step 1: Write the failing test**

Create `tests/web/__init__.py` and `tests/web/test_agents_api.py`:

```python
# tests/web/__init__.py
```

```python
# tests/web/test_agents_api.py
"""Tests for agent DB schema and API."""

import asyncio
import os
import pytest
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set")


@pytest.fixture
async def db_pool():
    """Create a connection pool for testing."""
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    yield pool
    await pool.close()


async def test_agents_table_exists(db_pool):
    """After ensure_schema, agents table should exist."""
    from bot.storage.db import ensure_schema
    await ensure_schema()

    async with db_pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'agents')"
        )
        assert exists is True


async def test_agent_documents_table_exists(db_pool):
    """After ensure_schema, agent_documents table should exist."""
    from bot.storage.db import ensure_schema
    await ensure_schema()

    async with db_pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_documents')"
        )
        assert exists is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/web/test_agents_api.py -v -k "test_agents_table_exists or test_agent_documents_table_exists"`
Expected: FAIL (tables don't exist yet)

- [ ] **Step 3: Add agents and agent_documents tables to ensure_schema()**

In `bot/storage/db.py`, inside `ensure_schema()`, after the existing `messages` table creation, add:

```python
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name         TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                emoji        TEXT NOT NULL DEFAULT '',
                config       JSONB NOT NULL DEFAULT '{}',
                enabled      BOOLEAN NOT NULL DEFAULT true,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_documents (
                id         BIGSERIAL PRIMARY KEY,
                agent_id   UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                doc_type   TEXT NOT NULL,
                content    TEXT NOT NULL DEFAULT '',
                version    INTEGER NOT NULL,
                message    TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (agent_id, doc_type, version)
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_docs_latest
            ON agent_documents (agent_id, doc_type, version DESC)
        """)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/web/test_agents_api.py -v -k "test_agents_table_exists or test_agent_documents_table_exists"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/storage/db.py tests/web/
git commit -m "feat: add agents + agent_documents tables to PostgreSQL schema"
```

---

## Task 2: Add FastAPI dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add fastapi and uvicorn to dependencies**

In `pyproject.toml`, add to the `dependencies` list:

```
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
```

- [ ] **Step 2: Run uv sync**

Run: `uv sync --dev`
Expected: packages install successfully

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add fastapi + uvicorn dependencies"
```

---

## Task 3: FastAPI backend — db helper and Pydantic models

**Files:**
- Create: `web/__init__.py`
- Create: `web/api/__init__.py`
- Create: `web/api/db.py`
- Create: `web/api/models.py`

- [ ] **Step 1: Create web/api/db.py**

```python
"""asyncpg pool management for the FastAPI service."""

from __future__ import annotations

import os
import ssl
import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the asyncpg connection pool, creating on first call."""
    global _pool
    if _pool is not None:
        return _pool

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    ssl_ctx = ssl.create_default_context()
    _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5, ssl=ssl_ctx)
    return _pool


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
```

- [ ] **Step 2: Create web/api/models.py**

```python
"""Pydantic request/response schemas for agent management API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Agent ────────────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    display_name: str
    emoji: str = ""
    config: dict = Field(default_factory=dict)
    enabled: bool = True
    soul: str = ""
    identity: str = ""
    user_doc: str = ""


class AgentUpdate(BaseModel):
    name: str | None = None
    display_name: str | None = None
    emoji: str | None = None
    config: dict | None = None
    enabled: bool | None = None


class AgentSummary(BaseModel):
    id: UUID
    name: str
    display_name: str
    emoji: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class DocumentVersion(BaseModel):
    id: int
    doc_type: str
    content: str
    version: int
    message: str
    created_by: str
    created_at: datetime


class AgentDetail(AgentSummary):
    config: dict
    documents: dict[str, DocumentVersion | None]  # doc_type -> latest version


# ── Document ─────────────────────────────────────────────────────────────────

class DocumentUpdate(BaseModel):
    content: str
    message: str = ""


class DocumentRollback(BaseModel):
    version: int
```

- [ ] **Step 3: Create empty __init__.py files**

```python
# web/__init__.py
```

```python
# web/api/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add web/
git commit -m "feat: add FastAPI db helper and Pydantic models"
```

---

## Task 4: FastAPI backend — agent CRUD routes

**Files:**
- Create: `web/api/routes/__init__.py`
- Create: `web/api/routes/agents.py`
- Test: `tests/web/test_agents_api.py`

- [ ] **Step 1: Write failing tests for agent CRUD**

Append to `tests/web/test_agents_api.py`:

```python
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def client():
    """Create a test client for the FastAPI app."""
    from web.api.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
async def clean_agents(db_pool):
    """Clean up agents table before each test."""
    yield
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM agent_documents")
        await conn.execute("DELETE FROM agents")


async def test_create_agent(client):
    resp = await client.post("/api/agents", json={
        "name": "test-bot",
        "display_name": "TestBot",
        "emoji": "🤖",
        "config": {"llm": {"provider": "anthropic"}},
        "soul": "You are a test bot.",
        "identity": "Name: TestBot",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-bot"
    assert data["display_name"] == "TestBot"
    assert "id" in data


async def test_list_agents(client):
    await client.post("/api/agents", json={
        "name": "bot-a", "display_name": "BotA",
    })
    await client.post("/api/agents", json={
        "name": "bot-b", "display_name": "BotB",
    })
    resp = await client.get("/api/agents")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


async def test_get_agent(client):
    create_resp = await client.post("/api/agents", json={
        "name": "detail-bot", "display_name": "DetailBot",
        "soul": "Some soul content",
    })
    agent_id = create_resp.json()["id"]
    resp = await client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "detail-bot"
    assert data["documents"]["soul"]["content"] == "Some soul content"
    assert data["documents"]["soul"]["version"] == 1


async def test_update_agent(client):
    create_resp = await client.post("/api/agents", json={
        "name": "upd-bot", "display_name": "UpdBot",
    })
    agent_id = create_resp.json()["id"]
    resp = await client.put(f"/api/agents/{agent_id}", json={
        "display_name": "UpdatedBot", "emoji": "🔥",
    })
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "UpdatedBot"
    assert resp.json()["emoji"] == "🔥"


async def test_delete_agent(client):
    create_resp = await client.post("/api/agents", json={
        "name": "del-bot", "display_name": "DelBot",
    })
    agent_id = create_resp.json()["id"]
    resp = await client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 204
    resp2 = await client.get(f"/api/agents/{agent_id}")
    assert resp2.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/web/test_agents_api.py -v -k "test_create or test_list or test_get_agent or test_update or test_delete"`
Expected: FAIL (routes and app don't exist yet)

- [ ] **Step 3: Create web/api/routes/agents.py**

```python
"""Agent CRUD endpoints."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException

from web.api.db import get_pool
from web.api.models import (
    AgentCreate, AgentUpdate, AgentSummary, AgentDetail, DocumentVersion,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])

DOC_TYPES = ("soul", "identity", "user_doc")


@router.get("", response_model=list[AgentSummary])
async def list_agents():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, display_name, emoji, enabled, created_at, updated_at "
            "FROM agents ORDER BY created_at"
        )
    return [dict(r) for r in rows]


@router.post("", response_model=AgentSummary, status_code=201)
async def create_agent(body: AgentCreate):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """INSERT INTO agents (name, display_name, emoji, config, enabled)
                   VALUES ($1, $2, $3, $4::jsonb, $5)
                   RETURNING id, name, display_name, emoji, enabled, created_at, updated_at""",
                body.name, body.display_name, body.emoji,
                json.dumps(body.config), body.enabled,
            )
            agent_id = row["id"]

            # Create initial v1 documents
            for doc_type, content in [
                ("soul", body.soul),
                ("identity", body.identity),
                ("user_doc", body.user_doc),
            ]:
                await conn.execute(
                    """INSERT INTO agent_documents (agent_id, doc_type, content, version, message, created_by)
                       VALUES ($1, $2, $3, 1, 'initial version', '')""",
                    agent_id, doc_type, content,
                )

    return dict(row)


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(agent_id: UUID):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, display_name, emoji, config, enabled, created_at, updated_at "
            "FROM agents WHERE id = $1", agent_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Fetch latest version of each doc type
        documents: dict[str, DocumentVersion | None] = {}
        for doc_type in DOC_TYPES:
            doc_row = await conn.fetchrow(
                """SELECT id, doc_type, content, version, message, created_by, created_at
                   FROM agent_documents
                   WHERE agent_id = $1 AND doc_type = $2
                   ORDER BY version DESC LIMIT 1""",
                agent_id, doc_type,
            )
            documents[doc_type] = dict(doc_row) if doc_row else None

    data = dict(row)
    data["config"] = json.loads(data["config"]) if isinstance(data["config"], str) else data["config"]
    data["documents"] = documents
    return data


@router.put("/{agent_id}", response_model=AgentSummary)
async def update_agent(agent_id: UUID, body: AgentUpdate):
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval("SELECT id FROM agents WHERE id = $1", agent_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Agent not found")

        sets: list[str] = []
        vals: list = []
        idx = 1

        for field_name in ("name", "display_name", "emoji", "enabled"):
            value = getattr(body, field_name)
            if value is not None:
                idx += 1
                sets.append(f"{field_name} = ${idx}")
                vals.append(value)

        if body.config is not None:
            idx += 1
            sets.append(f"config = ${idx}::jsonb")
            vals.append(json.dumps(body.config))

        if not sets:
            raise HTTPException(status_code=400, detail="No fields to update")

        sets.append("updated_at = now()")
        query = f"UPDATE agents SET {', '.join(sets)} WHERE id = $1 RETURNING id, name, display_name, emoji, enabled, created_at, updated_at"
        row = await conn.fetchrow(query, agent_id, *vals)

    return dict(row)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: UUID):
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM agents WHERE id = $1", agent_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Agent not found")
```

- [ ] **Step 4: Create web/api/routes/__init__.py**

```python
from web.api.routes.agents import router as agents_router
from web.api.routes.documents import router as documents_router

__all__ = ["agents_router", "documents_router"]
```

- [ ] **Step 5: Create web/api/main.py (FastAPI app)**

```python
"""FastAPI management API for miniclaw agents."""

from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.api.db import get_pool, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    await get_pool()

    # Ensure schema exists
    from bot.storage.db import ensure_schema
    await ensure_schema()

    yield
    await close_pool()


app = FastAPI(title="MiniClaw Agent Management", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from web.api.routes.agents import router as agents_router
app.include_router(agents_router)
```

Note: `documents_router` import in `routes/__init__.py` will fail until Task 5. That's fine — `main.py` imports the router directly.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/web/test_agents_api.py -v`
Expected: PASS (skip if DATABASE_URL not set)

- [ ] **Step 7: Commit**

```bash
git add web/api/ tests/web/
git commit -m "feat: add FastAPI agent CRUD routes with tests"
```

---

## Task 5: FastAPI backend — document version routes

**Files:**
- Create: `web/api/routes/documents.py`
- Test: `tests/web/test_documents_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/web/test_documents_api.py`:

```python
"""Tests for document version management API."""

import os
import pytest
import asyncpg
from httpx import AsyncClient, ASGITransport

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set")


@pytest.fixture
async def db_pool():
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    yield pool
    await pool.close()


@pytest.fixture
async def client():
    from web.api.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def agent_id(client):
    """Create a test agent and return its ID."""
    resp = await client.post("/api/agents", json={
        "name": "doc-test-bot",
        "display_name": "DocTestBot",
        "soul": "Original soul v1",
        "identity": "Original identity v1",
    })
    return resp.json()["id"]


@pytest.fixture(autouse=True)
async def clean_agents(db_pool):
    yield
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM agent_documents")
        await conn.execute("DELETE FROM agents")


async def test_get_latest_document(client, agent_id):
    resp = await client.get(f"/api/agents/{agent_id}/documents/soul")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "Original soul v1"
    assert data["version"] == 1


async def test_update_document_creates_new_version(client, agent_id):
    resp = await client.put(f"/api/agents/{agent_id}/documents/soul", json={
        "content": "Updated soul v2",
        "message": "made it better",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 2
    assert data["content"] == "Updated soul v2"

    # Latest should be v2
    latest = await client.get(f"/api/agents/{agent_id}/documents/soul")
    assert latest.json()["version"] == 2


async def test_document_history(client, agent_id):
    await client.put(f"/api/agents/{agent_id}/documents/soul", json={
        "content": "v2 content", "message": "v2",
    })
    await client.put(f"/api/agents/{agent_id}/documents/soul", json={
        "content": "v3 content", "message": "v3",
    })
    resp = await client.get(f"/api/agents/{agent_id}/documents/soul/history")
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) == 3
    assert history[0]["version"] == 3  # newest first
    assert history[2]["version"] == 1


async def test_get_specific_version(client, agent_id):
    await client.put(f"/api/agents/{agent_id}/documents/soul", json={
        "content": "v2 content",
    })
    resp = await client.get(f"/api/agents/{agent_id}/documents/soul/versions/1")
    assert resp.status_code == 200
    assert resp.json()["content"] == "Original soul v1"


async def test_rollback(client, agent_id):
    await client.put(f"/api/agents/{agent_id}/documents/soul", json={
        "content": "v2 content",
    })
    resp = await client.post(f"/api/agents/{agent_id}/documents/soul/rollback", json={
        "version": 1,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 3  # rollback creates v3
    assert data["content"] == "Original soul v1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/web/test_documents_api.py -v`
Expected: FAIL (documents router doesn't exist)

- [ ] **Step 3: Create web/api/routes/documents.py**

```python
"""Document version management endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from web.api.db import get_pool
from web.api.models import DocumentVersion, DocumentUpdate, DocumentRollback

router = APIRouter(prefix="/api/agents/{agent_id}/documents", tags=["documents"])

VALID_DOC_TYPES = {"soul", "identity", "user_doc"}


def _check_doc_type(doc_type: str) -> None:
    if doc_type not in VALID_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid doc_type: {doc_type}. Must be one of {VALID_DOC_TYPES}")


async def _check_agent_exists(conn, agent_id: UUID) -> None:
    exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM agents WHERE id = $1)", agent_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Agent not found")


@router.get("/{doc_type}", response_model=DocumentVersion)
async def get_latest_document(agent_id: UUID, doc_type: str):
    _check_doc_type(doc_type)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _check_agent_exists(conn, agent_id)
        row = await conn.fetchrow(
            """SELECT id, doc_type, content, version, message, created_by, created_at
               FROM agent_documents
               WHERE agent_id = $1 AND doc_type = $2
               ORDER BY version DESC LIMIT 1""",
            agent_id, doc_type,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)


@router.get("/{doc_type}/history", response_model=list[DocumentVersion])
async def get_document_history(agent_id: UUID, doc_type: str):
    _check_doc_type(doc_type)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _check_agent_exists(conn, agent_id)
        rows = await conn.fetch(
            """SELECT id, doc_type, content, version, message, created_by, created_at
               FROM agent_documents
               WHERE agent_id = $1 AND doc_type = $2
               ORDER BY version DESC""",
            agent_id, doc_type,
        )
    return [dict(r) for r in rows]


@router.get("/{doc_type}/versions/{version}", response_model=DocumentVersion)
async def get_document_version(agent_id: UUID, doc_type: str, version: int):
    _check_doc_type(doc_type)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _check_agent_exists(conn, agent_id)
        row = await conn.fetchrow(
            """SELECT id, doc_type, content, version, message, created_by, created_at
               FROM agent_documents
               WHERE agent_id = $1 AND doc_type = $2 AND version = $3""",
            agent_id, doc_type, version,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Version not found")
    return dict(row)


@router.put("/{doc_type}", response_model=DocumentVersion)
async def update_document(agent_id: UUID, doc_type: str, body: DocumentUpdate):
    _check_doc_type(doc_type)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _check_agent_exists(conn, agent_id)

            # Get current max version
            max_ver = await conn.fetchval(
                "SELECT COALESCE(MAX(version), 0) FROM agent_documents WHERE agent_id = $1 AND doc_type = $2",
                agent_id, doc_type,
            )
            new_version = max_ver + 1

            row = await conn.fetchrow(
                """INSERT INTO agent_documents (agent_id, doc_type, content, version, message, created_by)
                   VALUES ($1, $2, $3, $4, $5, '')
                   RETURNING id, doc_type, content, version, message, created_by, created_at""",
                agent_id, doc_type, body.content, new_version, body.message,
            )

            # Touch agent updated_at
            await conn.execute("UPDATE agents SET updated_at = now() WHERE id = $1", agent_id)

    return dict(row)


@router.post("/{doc_type}/rollback", response_model=DocumentVersion)
async def rollback_document(agent_id: UUID, doc_type: str, body: DocumentRollback):
    _check_doc_type(doc_type)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _check_agent_exists(conn, agent_id)

            # Get the target version's content
            target = await conn.fetchrow(
                """SELECT content FROM agent_documents
                   WHERE agent_id = $1 AND doc_type = $2 AND version = $3""",
                agent_id, doc_type, body.version,
            )
            if not target:
                raise HTTPException(status_code=404, detail=f"Version {body.version} not found")

            # Create a new version with the old content
            max_ver = await conn.fetchval(
                "SELECT COALESCE(MAX(version), 0) FROM agent_documents WHERE agent_id = $1 AND doc_type = $2",
                agent_id, doc_type,
            )
            new_version = max_ver + 1

            row = await conn.fetchrow(
                """INSERT INTO agent_documents (agent_id, doc_type, content, version, message, created_by)
                   VALUES ($1, $2, $3, $4, $5, '')
                   RETURNING id, doc_type, content, version, message, created_by, created_at""",
                agent_id, doc_type, target["content"], new_version,
                f"rollback to v{body.version}",
            )

            await conn.execute("UPDATE agents SET updated_at = now() WHERE id = $1", agent_id)

    return dict(row)
```

- [ ] **Step 4: Register documents router in main.py**

In `web/api/main.py`, after the agents router import, add:

```python
from web.api.routes.documents import router as documents_router
app.include_router(documents_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/web/test_documents_api.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/api/routes/documents.py tests/web/test_documents_api.py web/api/main.py
git commit -m "feat: add document version CRUD routes with tests"
```

---

## Task 6: Bot agent loader — add DB loading path

**Files:**
- Modify: `bot/agent.py`
- Test: manual (requires running bot with DATABASE_URL + agents in DB)

- [ ] **Step 1: Add _load_from_db() to bot/agent.py**

Add this function before `_load_from_json()`:

```python
async def _load_from_db() -> list[Agent] | None:
    """Try to load agents from PostgreSQL. Returns None if DB is not available or has no agents."""
    from bot.storage.db import use_postgres, get_pool

    if not use_postgres():
        return None

    try:
        pool = await get_pool()
    except Exception as e:
        log.warning("failed to connect to PostgreSQL for agent loading: %s", e)
        return None

    if pool is None:
        return None

    agents = []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, display_name, emoji, config, enabled FROM agents WHERE enabled = true"
        )

        for row in rows:
            import json as _json
            config_raw = row["config"]
            config_dict = _json.loads(config_raw) if isinstance(config_raw, str) else dict(config_raw)

            # Extract discord token from config
            discord_cfg = config_dict.get("discord", {})
            discord_token = discord_cfg.get("bot_token", "")

            # Extract LLM overrides from config
            llm_cfg = config_dict.get("llm", {})
            provider = llm_cfg.get("provider", "")
            model = ""
            if provider == "codex":
                model = llm_cfg.get("codex", {}).get("model", "")
            elif provider == "anthropic":
                model = llm_cfg.get("anthropic", {}).get("model", "")

            # Load latest documents
            soul = identity = user_doc = ""
            for doc_type in ("soul", "identity", "user_doc"):
                doc_row = await conn.fetchrow(
                    """SELECT content FROM agent_documents
                       WHERE agent_id = $1 AND doc_type = $2
                       ORDER BY version DESC LIMIT 1""",
                    row["id"], doc_type,
                )
                if doc_row:
                    if doc_type == "soul":
                        soul = doc_row["content"]
                    elif doc_type == "identity":
                        identity = doc_row["content"]
                    else:
                        user_doc = doc_row["content"]

            # Build system prompt from documents
            parts = [p for p in (soul, identity, user_doc) if p.strip()]
            if not parts:
                parts = ["You are a helpful assistant."]

            # Load skills
            from bot.config import SKILLS_DIR
            from bot.skills import load_skills, build_skills_prompt
            skills = load_skills(SKILLS_DIR)
            skills_prompt = build_skills_prompt(skills)
            if skills_prompt:
                parts.append(skills_prompt)

            system_prompt = "\n\n---\n\n".join(parts)

            # Use a temp workspace dir for memory/sessions (per agent name)
            workspace_dir = PROJECT_ROOT / f"workspace_{row['name']}"
            workspace_dir.mkdir(parents=True, exist_ok=True)

            agents.append(Agent(
                name=row["name"],
                discord_token=discord_token,
                workspace_dir=workspace_dir,
                system_prompt=system_prompt,
                model=model,
                provider=provider,
            ))
            log.info("loaded agent '%s' from DB (enabled=%s)", row["name"], row["enabled"])

    return agents if agents else None
```

- [ ] **Step 2: Update load_agents() to try DB first**

Replace the current `load_agents()` function:

```python
def load_agents(only: list[str] | None = None) -> list[Agent]:
    """Load agents from DB first, then agents.json, then .env.

    Args:
        only: If provided, only load agents whose names are in this list.
    """
    import asyncio

    # Try DB first
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context — can't use asyncio.run
            # This path is used during startup from main.py
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                agents = pool.submit(asyncio.run, _load_from_db()).result()
        else:
            agents = asyncio.run(_load_from_db())
    except Exception as e:
        log.warning("DB agent loading failed: %s, falling back", e)
        agents = None

    if agents:
        log.info("loaded %d agent(s) from database", len(agents))
    else:
        # Fallback: agents.json then .env
        agents = _load_from_json()
        if not agents:
            log.info("agents.json not found or empty, falling back to .env")
            agents = _load_from_env()

    if only:
        names = {n.lower() for n in only}
        agents = [a for a in agents if a.name.lower() in names]
        if not agents:
            raise SystemExit(f"No matching agents for --only {', '.join(only)}")

    if not agents:
        raise SystemExit("No enabled agents found. Check DB, agents.json, or .env.")

    return agents
```

- [ ] **Step 3: Make load_agents async-friendly from main.py**

Since `main.py` is already async, update `load_agents` to be simpler. Replace the function with an async version and update `main.py`:

In `bot/agent.py`, replace `load_agents` with:

```python
async def load_agents_async(only: list[str] | None = None) -> list[Agent]:
    """Async version: load agents from DB first, then agents.json, then .env."""
    agents = await _load_from_db()

    if agents:
        log.info("loaded %d agent(s) from database", len(agents))
    else:
        agents = _load_from_json()
        if not agents:
            log.info("agents.json not found or empty, falling back to .env")
            agents = _load_from_env()

    if only:
        names = {n.lower() for n in only}
        agents = [a for a in agents if a.name.lower() in names]
        if not agents:
            raise SystemExit(f"No matching agents for --only {', '.join(only)}")

    if not agents:
        raise SystemExit("No enabled agents found. Check DB, agents.json, or .env.")

    return agents


def load_agents(only: list[str] | None = None) -> list[Agent]:
    """Sync wrapper — kept for backward compatibility. Prefer load_agents_async."""
    agents = _load_from_json()
    if not agents:
        log.info("agents.json not found or empty, falling back to .env")
        agents = _load_from_env()

    if only:
        names = {n.lower() for n in only}
        agents = [a for a in agents if a.name.lower() in names]
        if not agents:
            raise SystemExit(f"No matching agents for --only {', '.join(only)}")

    if not agents:
        raise SystemExit("No enabled agents found. Check agents.json or .env.")

    return agents
```

- [ ] **Step 4: Update main.py to use load_agents_async**

In `main.py`, change the import and call:

```python
from bot.agent import load_agents_async
```

And in the `main()` function, replace:

```python
    agents = load_agents(only=_only_agents)
```

with:

```python
    agents = await load_agents_async(only=_only_agents)
```

- [ ] **Step 5: Run existing tests to verify nothing is broken**

Run: `uv run pytest tests/ -v --ignore=tests/web -q`
Expected: All existing tests PASS (DB path is skipped when DATABASE_URL is not set)

- [ ] **Step 6: Commit**

```bash
git add bot/agent.py main.py
git commit -m "feat: load agents from PostgreSQL with fallback to JSON/.env"
```

---

## Task 7: Migration script — seed DB from current workspace files

**Files:**
- Create: `scripts/migrate_agents_to_db.py`

- [ ] **Step 1: Create the migration script**

```python
"""One-time migration: read current workspace files + agents.json and insert into PostgreSQL."""

import asyncio
import json
import os
import ssl
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT_ROOT = Path(__file__).parent.parent


async def migrate():
    import asyncpg

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print("DATABASE_URL not set. Exiting.")
        return

    ssl_ctx = ssl.create_default_context()
    conn = await asyncpg.connect(database_url, ssl=ssl_ctx)

    try:
        # Ensure schema exists
        from bot.storage.db import ensure_schema
        await ensure_schema()

        # Load agents.json if it exists
        agents_json = PROJECT_ROOT / "agents.json"
        if agents_json.exists():
            with open(agents_json) as f:
                data = json.load(f)
            entries = data.get("agents", [])
        else:
            # Single agent from .env
            entries = [{
                "name": "default",
                "discord_token": os.getenv("DISCORD_BOT_TOKEN", ""),
                "workspace": "workspace",
                "enabled": True,
            }]

        for entry in entries:
            name = entry.get("name", "default")
            workspace = entry.get("workspace", "workspace")
            workspace_path = Path(workspace)
            if not workspace_path.is_absolute():
                workspace_path = PROJECT_ROOT / workspace_path

            # Check if agent already exists
            existing = await conn.fetchval(
                "SELECT id FROM agents WHERE name = $1", name
            )
            if existing:
                print(f"Agent '{name}' already exists in DB, skipping.")
                continue

            # Read workspace files
            soul = ""
            identity = ""
            user_doc = ""
            for filename, attr in [("SOUL.md", "soul"), ("IDENTITY.md", "identity"), ("USER.md", "user_doc")]:
                filepath = workspace_path / filename
                if filepath.exists():
                    content = filepath.read_text().strip()
                    if attr == "soul":
                        soul = content
                    elif attr == "identity":
                        identity = content
                    else:
                        user_doc = content

            # Build config from existing config.yaml + agent entry
            config = {
                "discord": {
                    "bot_token": entry.get("discord_token", ""),
                },
                "llm": {
                    "provider": entry.get("provider", "anthropic"),
                },
            }
            if entry.get("model"):
                provider = config["llm"]["provider"]
                config["llm"][provider] = {"model": entry["model"]}

            # Parse display_name from IDENTITY.md
            display_name = name
            for line in identity.split("\n"):
                if "**Name:**" in line:
                    display_name = line.split("**Name:**")[1].strip()
                    break

            # Parse emoji from IDENTITY.md
            emoji = ""
            for line in identity.split("\n"):
                if "**Emoji:**" in line:
                    emoji = line.split("**Emoji:**")[1].strip()
                    break

            # Insert agent
            agent_id = await conn.fetchval(
                """INSERT INTO agents (name, display_name, emoji, config, enabled)
                   VALUES ($1, $2, $3, $4::jsonb, $5)
                   RETURNING id""",
                name, display_name, emoji, json.dumps(config),
                entry.get("enabled", True),
            )

            # Insert initial document versions
            for doc_type, content in [("soul", soul), ("identity", identity), ("user_doc", user_doc)]:
                await conn.execute(
                    """INSERT INTO agent_documents (agent_id, doc_type, content, version, message, created_by)
                       VALUES ($1, $2, $3, 1, 'migrated from workspace files', 'migration')""",
                    agent_id, doc_type, content,
                )

            print(f"Migrated agent '{name}' (display={display_name}, emoji={emoji})")

    finally:
        await conn.close()

    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
```

- [ ] **Step 2: Ensure scripts/ directory exists**

Run: `ls scripts/` (should already exist from agent_cli.py reference in main.py)

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_agents_to_db.py
git commit -m "feat: add migration script to seed agents from workspace files to DB"
```

---

## Task 8: React frontend — project scaffold with Bun

**Files:**
- Create: `web/app/` (Vite + React + TypeScript project)

- [ ] **Step 1: Scaffold Vite project with Bun**

```bash
cd web && bun create vite app --template react-ts
cd app && bun install
```

- [ ] **Step 2: Install UI dependencies**

```bash
cd web/app
bun add react-router-dom
bun add -d tailwindcss @tailwindcss/vite
```

- [ ] **Step 3: Configure Tailwind**

Replace `web/app/src/index.css` with:

```css
@import "tailwindcss";
```

Update `web/app/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 4: Create API client**

Create `web/app/src/lib/api.ts`:

```typescript
const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || resp.statusText);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

export interface AgentSummary {
  id: string;
  name: string;
  display_name: string;
  emoji: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocumentVersion {
  id: number;
  doc_type: string;
  content: string;
  version: number;
  message: string;
  created_by: string;
  created_at: string;
}

export interface AgentDetail extends AgentSummary {
  config: Record<string, unknown>;
  documents: Record<string, DocumentVersion | null>;
}

export interface AgentCreate {
  name: string;
  display_name: string;
  emoji?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
  soul?: string;
  identity?: string;
  user_doc?: string;
}

export const api = {
  listAgents: () => request<AgentSummary[]>('/agents'),

  createAgent: (data: AgentCreate) =>
    request<AgentSummary>('/agents', { method: 'POST', body: JSON.stringify(data) }),

  getAgent: (id: string) => request<AgentDetail>(`/agents/${id}`),

  updateAgent: (id: string, data: Partial<AgentCreate>) =>
    request<AgentSummary>(`/agents/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  deleteAgent: (id: string) =>
    request<void>(`/agents/${id}`, { method: 'DELETE' }),

  getDocument: (agentId: string, docType: string) =>
    request<DocumentVersion>(`/agents/${agentId}/documents/${docType}`),

  getDocumentHistory: (agentId: string, docType: string) =>
    request<DocumentVersion[]>(`/agents/${agentId}/documents/${docType}/history`),

  getDocumentVersion: (agentId: string, docType: string, version: number) =>
    request<DocumentVersion>(`/agents/${agentId}/documents/${docType}/versions/${version}`),

  updateDocument: (agentId: string, docType: string, content: string, message?: string) =>
    request<DocumentVersion>(`/agents/${agentId}/documents/${docType}`, {
      method: 'PUT',
      body: JSON.stringify({ content, message: message || '' }),
    }),

  rollbackDocument: (agentId: string, docType: string, version: number) =>
    request<DocumentVersion>(`/agents/${agentId}/documents/${docType}/rollback`, {
      method: 'POST',
      body: JSON.stringify({ version }),
    }),
};
```

- [ ] **Step 5: Commit scaffold**

```bash
git add web/app/
git commit -m "feat: scaffold React frontend with Vite + Bun + Tailwind"
```

---

## Task 9: React frontend — Agent List page

**Files:**
- Create: `web/app/src/pages/AgentList.tsx`
- Create: `web/app/src/components/AgentCard.tsx`
- Modify: `web/app/src/App.tsx`

- [ ] **Step 1: Create AgentCard component**

Create `web/app/src/components/AgentCard.tsx`:

```tsx
import { AgentSummary } from '../lib/api';

interface Props {
  agent: AgentSummary;
  onToggle: (id: string, enabled: boolean) => void;
  onDelete: (id: string) => void;
  onClick: (id: string) => void;
}

export function AgentCard({ agent, onToggle, onDelete, onClick }: Props) {
  return (
    <div
      className="border border-zinc-700 rounded-lg p-4 bg-zinc-900 hover:border-zinc-500 cursor-pointer transition-colors"
      onClick={() => onClick(agent.id)}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{agent.emoji || '🤖'}</span>
          <div>
            <h3 className="text-lg font-semibold text-zinc-100">{agent.display_name}</h3>
            <p className="text-sm text-zinc-400">{agent.name}</p>
          </div>
        </div>
        <button
          className={`px-3 py-1 rounded text-sm font-medium ${
            agent.enabled
              ? 'bg-green-900 text-green-300'
              : 'bg-zinc-800 text-zinc-400'
          }`}
          onClick={(e) => {
            e.stopPropagation();
            onToggle(agent.id, !agent.enabled);
          }}
        >
          {agent.enabled ? 'Enabled' : 'Disabled'}
        </button>
      </div>
      <div className="flex justify-between items-center text-xs text-zinc-500 mt-3">
        <span>Updated {new Date(agent.updated_at).toLocaleDateString()}</span>
        <button
          className="text-red-400 hover:text-red-300"
          onClick={(e) => {
            e.stopPropagation();
            if (confirm(`Delete agent "${agent.display_name}"?`)) {
              onDelete(agent.id);
            }
          }}
        >
          Delete
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create AgentList page**

Create `web/app/src/pages/AgentList.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, AgentSummary } from '../lib/api';
import { AgentCard } from '../components/AgentCard';

export function AgentList() {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDisplayName, setNewDisplayName] = useState('');
  const [newEmoji, setNewEmoji] = useState('');
  const navigate = useNavigate();

  const fetchAgents = async () => {
    setLoading(true);
    try {
      setAgents(await api.listAgents());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAgents(); }, []);

  const handleToggle = async (id: string, enabled: boolean) => {
    await api.updateAgent(id, { enabled });
    await fetchAgents();
  };

  const handleDelete = async (id: string) => {
    await api.deleteAgent(id);
    await fetchAgents();
  };

  const handleCreate = async () => {
    if (!newName || !newDisplayName) return;
    await api.createAgent({
      name: newName,
      display_name: newDisplayName,
      emoji: newEmoji,
    });
    setShowCreate(false);
    setNewName('');
    setNewDisplayName('');
    setNewEmoji('');
    await fetchAgents();
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-zinc-100">Agents</h1>
        <button
          className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded"
          onClick={() => setShowCreate(true)}
        >
          + New Agent
        </button>
      </div>

      {showCreate && (
        <div className="border border-zinc-700 rounded-lg p-4 bg-zinc-900 mb-6">
          <h2 className="text-lg font-semibold text-zinc-100 mb-3">Create Agent</h2>
          <div className="grid grid-cols-3 gap-3 mb-3">
            <input
              placeholder="name (slug)"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="bg-zinc-800 border border-zinc-600 rounded px-3 py-2 text-zinc-100"
            />
            <input
              placeholder="Display Name"
              value={newDisplayName}
              onChange={(e) => setNewDisplayName(e.target.value)}
              className="bg-zinc-800 border border-zinc-600 rounded px-3 py-2 text-zinc-100"
            />
            <input
              placeholder="Emoji"
              value={newEmoji}
              onChange={(e) => setNewEmoji(e.target.value)}
              className="bg-zinc-800 border border-zinc-600 rounded px-3 py-2 text-zinc-100"
            />
          </div>
          <div className="flex gap-2">
            <button
              className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded"
              onClick={handleCreate}
            >
              Create
            </button>
            <button
              className="bg-zinc-700 hover:bg-zinc-600 text-zinc-300 px-4 py-2 rounded"
              onClick={() => setShowCreate(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-zinc-400">Loading...</p>
      ) : agents.length === 0 ? (
        <p className="text-zinc-400">No agents yet. Create one to get started.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onToggle={handleToggle}
              onDelete={handleDelete}
              onClick={(id) => navigate(`/agents/${id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Update App.tsx with routing**

Replace `web/app/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AgentList } from './pages/AgentList';
import { AgentDetail } from './pages/AgentDetail';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-zinc-950 text-zinc-100">
        <Routes>
          <Route path="/" element={<Navigate to="/agents" replace />} />
          <Route path="/agents" element={<AgentList />} />
          <Route path="/agents/:id" element={<AgentDetail />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
```

- [ ] **Step 4: Create a placeholder AgentDetail page** (will be built in next task)

Create `web/app/src/pages/AgentDetail.tsx`:

```tsx
export function AgentDetail() {
  return <div className="p-6 text-zinc-400">Agent detail page — coming next...</div>;
}
```

- [ ] **Step 5: Clean up default Vite files**

Delete `web/app/src/App.css` and `web/app/src/assets/` if they exist. Update `web/app/src/main.tsx` to only import `index.css`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 6: Test locally**

```bash
cd web/app && bun run dev
# Open http://localhost:3000 — should show agent list (empty or with data if API is running)
```

- [ ] **Step 7: Commit**

```bash
git add web/app/
git commit -m "feat: add Agent List page with create/toggle/delete"
```

---

## Task 10: React frontend — Agent Detail page with document editor and version history

**Files:**
- Modify: `web/app/src/pages/AgentDetail.tsx`
- Create: `web/app/src/components/DocumentEditor.tsx`
- Create: `web/app/src/components/VersionHistory.tsx`
- Create: `web/app/src/components/ConfigEditor.tsx`

- [ ] **Step 1: Create DocumentEditor component**

Create `web/app/src/components/DocumentEditor.tsx`:

```tsx
import { useState } from 'react';

interface Props {
  content: string;
  onSave: (content: string, message: string) => Promise<void>;
}

export function DocumentEditor({ content, onSave }: Props) {
  const [text, setText] = useState(content);
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState(false);

  const dirty = text !== content;

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(text, message);
      setMessage('');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 mb-2">
        <button
          className={`px-3 py-1 rounded text-sm ${!preview ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400'}`}
          onClick={() => setPreview(false)}
        >
          Edit
        </button>
        <button
          className={`px-3 py-1 rounded text-sm ${preview ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-400'}`}
          onClick={() => setPreview(true)}
        >
          Preview
        </button>
      </div>

      {preview ? (
        <pre className="flex-1 bg-zinc-900 border border-zinc-700 rounded p-4 overflow-auto whitespace-pre-wrap text-sm text-zinc-300">
          {text}
        </pre>
      ) : (
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="flex-1 bg-zinc-900 border border-zinc-700 rounded p-4 text-sm text-zinc-100 font-mono resize-none focus:outline-none focus:border-zinc-500"
          spellCheck={false}
        />
      )}

      {dirty && (
        <div className="flex items-center gap-2 mt-3">
          <input
            placeholder="Version note (optional)"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            className="flex-1 bg-zinc-800 border border-zinc-600 rounded px-3 py-2 text-sm text-zinc-100"
          />
          <button
            className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
          <button
            className="bg-zinc-700 hover:bg-zinc-600 text-zinc-300 px-4 py-2 rounded text-sm"
            onClick={() => setText(content)}
          >
            Discard
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create VersionHistory component**

Create `web/app/src/components/VersionHistory.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { api, DocumentVersion } from '../lib/api';

interface Props {
  agentId: string;
  docType: string;
  currentVersion: number;
  onRollback: () => void;
}

export function VersionHistory({ agentId, docType, currentVersion, onRollback }: Props) {
  const [history, setHistory] = useState<DocumentVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    setLoading(true);
    api.getDocumentHistory(agentId, docType)
      .then(setHistory)
      .finally(() => setLoading(false));
  }, [agentId, docType, currentVersion]);

  const handleRollback = async (version: number) => {
    if (!confirm(`Rollback to v${version}? This creates a new version.`)) return;
    await api.rollbackDocument(agentId, docType, version);
    onRollback();
  };

  if (loading) return <p className="text-zinc-400 text-sm p-2">Loading history...</p>;

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-zinc-300 mb-2">Version History</h3>
      {history.map((v) => (
        <div
          key={v.id}
          className={`border rounded p-2 text-sm cursor-pointer transition-colors ${
            v.version === currentVersion
              ? 'border-blue-600 bg-blue-950'
              : 'border-zinc-700 bg-zinc-900 hover:border-zinc-500'
          }`}
          onClick={() => setExpandedId(expandedId === v.id ? null : v.id)}
        >
          <div className="flex justify-between items-center">
            <span className="text-zinc-100 font-medium">v{v.version}</span>
            <span className="text-zinc-500 text-xs">
              {new Date(v.created_at).toLocaleString()}
            </span>
          </div>
          {v.message && <p className="text-zinc-400 text-xs mt-1">{v.message}</p>}

          {expandedId === v.id && (
            <div className="mt-2">
              <pre className="bg-zinc-800 rounded p-2 text-xs text-zinc-300 max-h-48 overflow-auto whitespace-pre-wrap">
                {v.content}
              </pre>
              {v.version !== currentVersion && (
                <button
                  className="mt-2 text-xs text-blue-400 hover:text-blue-300"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRollback(v.version);
                  }}
                >
                  Rollback to this version
                </button>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Create ConfigEditor component**

Create `web/app/src/components/ConfigEditor.tsx`:

```tsx
import { useState } from 'react';

interface Props {
  config: Record<string, unknown>;
  onSave: (config: Record<string, unknown>) => Promise<void>;
}

export function ConfigEditor({ config, onSave }: Props) {
  const [text, setText] = useState(JSON.stringify(config, null, 2));
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const original = JSON.stringify(config, null, 2);
  const dirty = text !== original;

  const handleSave = async () => {
    try {
      const parsed = JSON.parse(text);
      setError('');
      setSaving(true);
      await onSave(parsed);
    } catch (e) {
      setError(e instanceof SyntaxError ? `Invalid JSON: ${e.message}` : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setError('');
        }}
        className="flex-1 bg-zinc-900 border border-zinc-700 rounded p-4 text-sm text-zinc-100 font-mono resize-none focus:outline-none focus:border-zinc-500"
        spellCheck={false}
      />
      {error && <p className="text-red-400 text-sm mt-2">{error}</p>}
      {dirty && (
        <div className="flex gap-2 mt-3">
          <button
            className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded text-sm disabled:opacity-50"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Config'}
          </button>
          <button
            className="bg-zinc-700 hover:bg-zinc-600 text-zinc-300 px-4 py-2 rounded text-sm"
            onClick={() => { setText(original); setError(''); }}
          >
            Discard
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Build the full AgentDetail page**

Replace `web/app/src/pages/AgentDetail.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api, AgentDetail as AgentDetailType } from '../lib/api';
import { DocumentEditor } from '../components/DocumentEditor';
import { VersionHistory } from '../components/VersionHistory';
import { ConfigEditor } from '../components/ConfigEditor';

const DOC_TABS = [
  { key: 'soul', label: 'Soul' },
  { key: 'identity', label: 'Identity' },
  { key: 'user_doc', label: 'User Doc' },
  { key: 'config', label: 'Config' },
] as const;

type TabKey = (typeof DOC_TABS)[number]['key'];

export function AgentDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<AgentDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabKey>('soul');

  const fetchAgent = async () => {
    if (!id) return;
    setLoading(true);
    try {
      setAgent(await api.getAgent(id));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAgent(); }, [id]);

  if (loading || !agent) {
    return <p className="p-6 text-zinc-400">Loading...</p>;
  }

  const currentDoc = activeTab !== 'config' ? agent.documents[activeTab] : null;

  const handleSaveDoc = async (content: string, message: string) => {
    if (!id || activeTab === 'config') return;
    await api.updateDocument(id, activeTab, content, message);
    await fetchAgent();
  };

  const handleSaveConfig = async (config: Record<string, unknown>) => {
    if (!id) return;
    await api.updateAgent(id, { config });
    await fetchAgent();
  };

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="flex items-center gap-3 mb-6">
        <button
          className="text-zinc-400 hover:text-zinc-200"
          onClick={() => navigate('/agents')}
        >
          ← Back
        </button>
        <span className="text-2xl">{agent.emoji || '🤖'}</span>
        <div>
          <h1 className="text-xl font-bold text-zinc-100">{agent.display_name}</h1>
          <p className="text-sm text-zinc-400">{agent.name}</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-zinc-700 mb-4">
        {DOC_TABS.map((tab) => (
          <button
            key={tab.key}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex gap-4" style={{ height: 'calc(100vh - 220px)' }}>
        <div className="flex-1">
          {activeTab === 'config' ? (
            <ConfigEditor config={agent.config} onSave={handleSaveConfig} />
          ) : (
            <DocumentEditor
              key={`${activeTab}-${currentDoc?.version}`}
              content={currentDoc?.content || ''}
              onSave={handleSaveDoc}
            />
          )}
        </div>

        {activeTab !== 'config' && currentDoc && (
          <div className="w-72 overflow-auto">
            <VersionHistory
              agentId={agent.id}
              docType={activeTab}
              currentVersion={currentDoc.version}
              onRollback={fetchAgent}
            />
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Test locally**

```bash
# Terminal 1: start FastAPI
cd web/api && DATABASE_URL=... uv run uvicorn web.api.main:app --reload --port 8000

# Terminal 2: start frontend
cd web/app && bun run dev

# Open http://localhost:3000 — create an agent, edit soul/identity, check version history
```

- [ ] **Step 6: Commit**

```bash
git add web/app/src/
git commit -m "feat: add Agent Detail page with document editor and version history"
```

---

## Task 11: Final wiring — run script for FastAPI and cleanup

**Files:**
- Modify: `README.md` (add management UI section)

- [ ] **Step 1: Update README.md with management UI instructions**

Add after the "Testing" section in `README.md`:

```markdown
## Agent Management UI

```bash
# Start the API server
DATABASE_URL=your-postgres-url uv run uvicorn web.api.main:app --port 8000

# Start the frontend (in a separate terminal)
cd web/app && bun run dev
```

Open http://localhost:3000 to manage agents.

### Migration from workspace files

If you have existing agents in `agents.json` or `workspace/`:

```bash
uv run python scripts/migrate_agents_to_db.py
```
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest tests/ -v -q
```
Expected: All existing tests PASS. Web tests SKIP if DATABASE_URL not set.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add agent management UI setup instructions to README"
```
