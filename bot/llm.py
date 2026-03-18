"""Unified LLM entry point — stream() and reply()."""

from collections.abc import AsyncIterator

from bot.message import Content
from bot.processor import StreamProcessor
from bot.provider import get_default_provider
from bot.provider.base import BaseProvider
from bot.session import SessionManager

# Global singletons
_session_mgr: SessionManager | None = None
_provider: BaseProvider | None = None


def _get_session_mgr() -> SessionManager:
    global _session_mgr
    if _session_mgr is None:
        _session_mgr = SessionManager()
    return _session_mgr


def _get_provider() -> BaseProvider:
    global _provider
    if _provider is None:
        _provider = get_default_provider()
    return _provider


async def stream(session_key: str, user_content: Content) -> AsyncIterator[str]:
    """Unified entry: stream LLM reply with tool loop."""
    processor = StreamProcessor(
        provider=_get_provider(),
        session=_get_session_mgr(),
        session_key=session_key,
    )
    async for chunk in processor.process(user_content):
        yield chunk


async def reply(session_key: str, user_content: Content) -> str:
    """Non-streaming entry: collect full reply."""
    chunks: list[str] = []
    async for chunk in stream(session_key, user_content):
        chunks.append(chunk)
    return "".join(chunks)
