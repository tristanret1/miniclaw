"""Pydantic v2 models for the agent management API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
    documents: dict[str, DocumentVersion | None]


class DocumentUpdate(BaseModel):
    content: str
    message: str = ""


class DocumentRollback(BaseModel):
    version: int
