"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx

from bot.message import Message


class BaseProvider(ABC):
    """LLM Provider abstract interface."""

    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Return a shared httpx.AsyncClient, creating it lazily."""
        if self._http is None or self._http.is_closed:
            from bot.config import get_config
            cfg = get_config().services.timeouts
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(cfg.http_read, connect=cfg.http_connect),
                http2=True,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._http

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
        self._http = None

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[dict]:
        """Stream LLM response, yield SSE event dicts."""
        ...

    @abstractmethod
    async def call(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """Non-streaming LLM call, return full response dict."""
        ...

    @abstractmethod
    async def refresh_auth(self) -> None:
        """Refresh authentication credentials."""
        ...
