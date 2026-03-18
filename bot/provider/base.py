"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from bot.message import Message


class BaseProvider(ABC):
    """LLM Provider abstract interface."""

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
