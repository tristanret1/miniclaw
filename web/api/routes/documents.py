"""Document version CRUD endpoints at /api/agents/{agent_id}/documents."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from web.api.db import get_pool
from web.api.models import DocumentRollback, DocumentUpdate, DocumentVersion

router = APIRouter(prefix="/api/agents/{agent_id}/documents", tags=["documents"])

VALID_DOC_TYPES = {"soul", "identity", "user_doc"}


def _check_doc_type(doc_type: str) -> None:
    if doc_type not in VALID_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid doc_type '{doc_type}'. Must be one of: {', '.join(sorted(VALID_DOC_TYPES))}",
        )


async def _check_agent_exists(conn, agent_id: UUID) -> None:
    row = await conn.fetchrow("SELECT id FROM agents WHERE id = $1", agent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")


def _row_to_doc_version(row) -> DocumentVersion:
    return DocumentVersion(
        id=row["id"],
        doc_type=row["doc_type"],
        content=row["content"],
        version=row["version"],
        message=row["message"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


@router.get("/{doc_type}", response_model=DocumentVersion)
async def get_latest_document(agent_id: UUID, doc_type: str):
    """Get the latest version of a document."""
    _check_doc_type(doc_type)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _check_agent_exists(conn, agent_id)
        row = await conn.fetchrow(
            """
            SELECT id, doc_type, content, version, message, created_by, created_at
            FROM agent_documents
            WHERE agent_id = $1 AND doc_type = $2
            ORDER BY version DESC
            LIMIT 1
            """,
            agent_id,
            doc_type,
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_type}' not found")
    return _row_to_doc_version(row)


@router.get("/{doc_type}/history", response_model=list[DocumentVersion])
async def get_document_history(agent_id: UUID, doc_type: str):
    """List all versions of a document, newest first."""
    _check_doc_type(doc_type)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _check_agent_exists(conn, agent_id)
        rows = await conn.fetch(
            """
            SELECT id, doc_type, content, version, message, created_by, created_at
            FROM agent_documents
            WHERE agent_id = $1 AND doc_type = $2
            ORDER BY version DESC
            """,
            agent_id,
            doc_type,
        )
    return [_row_to_doc_version(r) for r in rows]


@router.get("/{doc_type}/versions/{version}", response_model=DocumentVersion)
async def get_document_version(agent_id: UUID, doc_type: str, version: int):
    """Get a specific version of a document."""
    _check_doc_type(doc_type)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _check_agent_exists(conn, agent_id)
        row = await conn.fetchrow(
            """
            SELECT id, doc_type, content, version, message, created_by, created_at
            FROM agent_documents
            WHERE agent_id = $1 AND doc_type = $2 AND version = $3
            """,
            agent_id,
            doc_type,
            version,
        )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{doc_type}' version {version} not found",
        )
    return _row_to_doc_version(row)


@router.put("/{doc_type}", response_model=DocumentVersion, status_code=201)
async def update_document(agent_id: UUID, doc_type: str, body: DocumentUpdate):
    """Create a new version of a document."""
    _check_doc_type(doc_type)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _check_agent_exists(conn, agent_id)
        async with conn.transaction():
            max_row = await conn.fetchrow(
                "SELECT COALESCE(MAX(version), 0) AS max_version FROM agent_documents "
                "WHERE agent_id = $1 AND doc_type = $2",
                agent_id,
                doc_type,
            )
            new_version = max_row["max_version"] + 1
            row = await conn.fetchrow(
                """
                INSERT INTO agent_documents (agent_id, doc_type, content, version, message, created_by)
                VALUES ($1, $2, $3, $4, $5, 'user')
                RETURNING id, doc_type, content, version, message, created_by, created_at
                """,
                agent_id,
                doc_type,
                body.content,
                new_version,
                body.message,
            )
            await conn.execute(
                "UPDATE agents SET updated_at = now() WHERE id = $1", agent_id
            )
    return _row_to_doc_version(row)


@router.post("/{doc_type}/rollback", response_model=DocumentVersion, status_code=201)
async def rollback_document(agent_id: UUID, doc_type: str, body: DocumentRollback):
    """Rollback a document to a specified version by inserting a new version with the old content."""
    _check_doc_type(doc_type)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _check_agent_exists(conn, agent_id)
        async with conn.transaction():
            target_row = await conn.fetchrow(
                """
                SELECT content FROM agent_documents
                WHERE agent_id = $1 AND doc_type = $2 AND version = $3
                """,
                agent_id,
                doc_type,
                body.version,
            )
            if target_row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document '{doc_type}' version {body.version} not found",
                )
            max_row = await conn.fetchrow(
                "SELECT COALESCE(MAX(version), 0) AS max_version FROM agent_documents "
                "WHERE agent_id = $1 AND doc_type = $2",
                agent_id,
                doc_type,
            )
            new_version = max_row["max_version"] + 1
            row = await conn.fetchrow(
                """
                INSERT INTO agent_documents (agent_id, doc_type, content, version, message, created_by)
                VALUES ($1, $2, $3, $4, $5, 'user')
                RETURNING id, doc_type, content, version, message, created_by, created_at
                """,
                agent_id,
                doc_type,
                target_row["content"],
                new_version,
                f"rollback to v{body.version}",
            )
            await conn.execute(
                "UPDATE agents SET updated_at = now() WHERE id = $1", agent_id
            )
    return _row_to_doc_version(row)
