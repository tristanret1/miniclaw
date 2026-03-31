"""Agent CRUD endpoints at /api/agents."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException
from starlette.responses import Response

from web.api.db import get_pool
from web.api.models import (
    AgentCreate,
    AgentDetail,
    AgentSummary,
    AgentUpdate,
    DocumentVersion,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _parse_config(raw) -> dict:
    """Handle asyncpg returning config as str or dict depending on version."""
    if isinstance(raw, str):
        return json.loads(raw)
    if raw is None:
        return {}
    return dict(raw)


def _row_to_summary(row) -> AgentSummary:
    return AgentSummary(
        id=row["id"],
        name=row["name"],
        display_name=row["display_name"],
        emoji=row["emoji"],
        enabled=row["enabled"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("", response_model=list[AgentSummary])
async def list_agents():
    """List all agents."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, display_name, emoji, enabled, created_at, updated_at "
            "FROM agents ORDER BY created_at ASC"
        )
    return [_row_to_summary(r) for r in rows]


@router.post("", response_model=AgentSummary, status_code=201)
async def create_agent(body: AgentCreate):
    """Create a new agent with initial v1 documents for soul, identity, user_doc."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                agent_row = await conn.fetchrow(
                    """
                    INSERT INTO agents (name, display_name, emoji, config, enabled)
                    VALUES ($1, $2, $3, $4::jsonb, $5)
                    RETURNING id, name, display_name, emoji, enabled, created_at, updated_at
                    """,
                    body.name,
                    body.display_name,
                    body.emoji,
                    json.dumps(body.config),
                    body.enabled,
                )
            except Exception as exc:
                if "unique" in str(exc).lower():
                    raise HTTPException(status_code=409, detail=f"Agent name '{body.name}' already exists")
                raise

            agent_id = agent_row["id"]

            # Insert initial v1 documents
            doc_pairs = [
                ("soul", body.soul),
                ("identity", body.identity),
                ("user_doc", body.user_doc),
            ]
            for doc_type, content in doc_pairs:
                await conn.execute(
                    """
                    INSERT INTO agent_documents (agent_id, doc_type, content, version, message, created_by)
                    VALUES ($1, $2, $3, 1, 'Initial version', 'system')
                    """,
                    agent_id,
                    doc_type,
                    content,
                )

    return _row_to_summary(agent_row)


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(agent_id: UUID):
    """Get agent detail with latest doc versions."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, display_name, emoji, config, enabled, created_at, updated_at "
            "FROM agents WHERE id = $1",
            agent_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Agent not found")

        doc_rows = await conn.fetch(
            """
            SELECT DISTINCT ON (doc_type)
                id, doc_type, content, version, message, created_by, created_at
            FROM agent_documents
            WHERE agent_id = $1
            ORDER BY doc_type, version DESC
            """,
            agent_id,
        )

    documents: dict[str, DocumentVersion | None] = {
        "soul": None,
        "identity": None,
        "user_doc": None,
    }
    for dr in doc_rows:
        documents[dr["doc_type"]] = DocumentVersion(
            id=dr["id"],
            doc_type=dr["doc_type"],
            content=dr["content"],
            version=dr["version"],
            message=dr["message"],
            created_by=dr["created_by"],
            created_at=dr["created_at"],
        )

    return AgentDetail(
        id=row["id"],
        name=row["name"],
        display_name=row["display_name"],
        emoji=row["emoji"],
        enabled=row["enabled"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        config=_parse_config(row["config"]),
        documents=documents,
    )


@router.put("/{agent_id}", response_model=AgentSummary)
async def update_agent(agent_id: UUID, body: AgentUpdate):
    """Update agent fields (only provided fields are updated)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM agents WHERE id = $1", agent_id
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Build SET clause dynamically from non-None fields
        updates = body.model_dump(exclude_none=True)
        if not updates:
            row = await conn.fetchrow(
                "SELECT id, name, display_name, emoji, enabled, created_at, updated_at "
                "FROM agents WHERE id = $1",
                agent_id,
            )
            return _row_to_summary(row)

        set_parts = []
        params = []
        idx = 1
        for field, value in updates.items():
            if field == "config":
                set_parts.append(f"{field} = ${idx}::jsonb")
                params.append(json.dumps(value))
            else:
                set_parts.append(f"{field} = ${idx}")
                params.append(value)
            idx += 1

        set_parts.append(f"updated_at = now()")
        params.append(agent_id)

        query = (
            f"UPDATE agents SET {', '.join(set_parts)} WHERE id = ${idx} "
            "RETURNING id, name, display_name, emoji, enabled, created_at, updated_at"
        )
        row = await conn.fetchrow(query, *params)

    return _row_to_summary(row)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: UUID):
    """Delete an agent (cascades to agent_documents)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM agents WHERE id = $1", agent_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Agent not found")
    return Response(status_code=204)
