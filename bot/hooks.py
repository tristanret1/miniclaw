"""Agent lifecycle hooks — generic callback registry.

Replaces hardcoded gateway imports in client.py. Any gateway
(API, PixelTown, etc.) can register callbacks to receive agent
status changes.
"""

from __future__ import annotations

from typing import Callable

_on_working: list[Callable[[str, str], None]] = []
_on_idle: list[Callable[[str], None]] = []


def register_on_working(cb: Callable[[str, str], None]) -> None:
    """Register callback for agent-starts-working events. Args: (agent_id, detail)."""
    _on_working.append(cb)


def register_on_idle(cb: Callable[[str], None]) -> None:
    """Register callback for agent-becomes-idle events. Args: (agent_id,)."""
    _on_idle.append(cb)


def fire_working(agent_id: str, detail: str = "") -> None:
    """Notify all listeners that an agent started working."""
    for cb in _on_working:
        try:
            cb(agent_id, detail)
        except Exception:
            pass


def fire_idle(agent_id: str) -> None:
    """Notify all listeners that an agent became idle."""
    for cb in _on_idle:
        try:
            cb(agent_id)
        except Exception:
            pass


def _reset() -> None:
    """Clear all registered hooks. For testing only."""
    _on_working.clear()
    _on_idle.clear()
