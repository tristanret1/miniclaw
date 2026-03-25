"""Unified LLM entry point — stream() and reply()."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from bot.message import Content
from bot.processor import StreamProcessor
from bot.provider import get_default_provider
from bot.provider.base import BaseProvider
from bot.session import SessionManager

if TYPE_CHECKING:
    from bot.agent import Agent

# Global provider singleton (shared across agents — stateless)
_provider: BaseProvider | None = None

# Default session manager (used when no agent is specified)
_default_session_mgr: SessionManager | None = None


def _get_provider() -> BaseProvider:
    global _provider
    if _provider is None:
        _provider = get_default_provider()
    return _provider


def _get_default_session_mgr() -> SessionManager:
    global _default_session_mgr
    if _default_session_mgr is None:
        _default_session_mgr = SessionManager()
    return _default_session_mgr


def _resolve(agent: Agent | None = None):
    """Resolve session manager, system prompt, memory dir, and agent name from agent or defaults."""
    if agent is not None:
        session_mgr = agent.session_mgr or _get_default_session_mgr()
        return session_mgr, agent.system_prompt, agent.memory_dir, agent.name
    return _get_default_session_mgr(), None, None, "default"


async def stream(session_key: str, user_content: Content,
                 agent: Agent | None = None) -> AsyncIterator[str]:
    """Unified entry: stream LLM reply with tool loop."""
    session_mgr, system_prompt, memory_dir, agent_name = _resolve(agent)
    processor = StreamProcessor(
        provider=_get_provider(),
        session=session_mgr,
        session_key=session_key,
        system_prompt=system_prompt,
        memory_dir=memory_dir,
        agent_name=agent_name,
    )
    async for chunk in processor.process(user_content):
        yield chunk


async def reply(session_key: str, user_content: Content,
                agent: Agent | None = None) -> str:
    """Non-streaming entry: collect full reply."""
    chunks: list[str] = []
    async for chunk in stream(session_key, user_content, agent=agent):
        chunks.append(chunk)
    return "".join(chunks)
