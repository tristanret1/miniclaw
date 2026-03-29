"""Agent status tracker — aggregates events, computes social affinity."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class AgentState:
    """Current state of a single agent."""

    status: str = "offline"  # idle | working | sleeping | socializing | offline
    detail: str = ""
    since: float = field(default_factory=time.time)


class AgentStatusTracker:
    """
    Tracks agent status from runtime events and computes social affinity.

    Event sources:
      - client.py → on_message processing start/end
      - cron.py   → job_started / job_finished
      - gateway/* → gateway-specific activity
    """

    def __init__(self, agent_ids: list[str], sleep_after_hour: int = 23) -> None:
        self._states: dict[str, AgentState] = {
            aid: AgentState() for aid in agent_ids
        }
        self._affinity: dict[tuple[str, str], float] = {}
        self._sleep_after = sleep_after_hour
        self._listeners: list[Callable[[str, AgentState], None]] = []

    # ── Event handlers ──

    def on_working(self, agent_id: str, detail: str = "") -> None:
        """Called when an agent starts processing work."""
        self._set(agent_id, "working", detail)

    def on_idle(self, agent_id: str) -> None:
        """Called when an agent finishes work."""
        self._set(agent_id, "idle", "")

    def on_offline(self, agent_id: str) -> None:
        """Called when an agent goes offline."""
        self._set(agent_id, "offline", "")

    def on_online(self, agent_id: str) -> None:
        """Called when an agent comes online."""
        self._set(agent_id, "idle", "")

    # ── Queries ──

    def get_status(self, agent_id: str) -> dict:
        """Get current status for one agent."""
        state = self._states.get(agent_id, AgentState())
        return {
            "status": state.status,
            "detail": state.detail,
            "since": state.since,
        }

    def get_all_statuses(self) -> dict[str, dict]:
        """Get status for all agents."""
        return {aid: self.get_status(aid) for aid in self._states}

    # ── Social affinity ──

    def get_affinity(self, agent_a: str, agent_b: str) -> float:
        """Get affinity score between two agents (0.0 - 1.0)."""
        key = tuple(sorted([agent_a, agent_b]))
        return self._affinity.get(key, 0.0)  # type: ignore[arg-type]

    def get_all_affinities(self) -> list[dict]:
        """Get all affinity pairs."""
        return [
            {"agents": list(pair), "score": score}
            for pair, score in self._affinity.items()
            if score > 0.01
        ]

    def compute_affinity(
        self, interaction_counts: dict[tuple[str, str], int], decay: float = 0.95
    ) -> None:
        """
        Recompute affinity scores from interaction overlap data.

        Args:
            interaction_counts: {(agent_a, agent_b): count} from sessions.db
            decay: Decay factor applied to existing scores before merging
        """
        # Apply decay to existing scores
        for key in self._affinity:
            self._affinity[key] *= decay

        # Merge new interaction data
        max_count = max(interaction_counts.values(), default=1)
        for pair, count in interaction_counts.items():
            key = tuple(sorted(pair))
            normalized = min(1.0, count / max_count)
            current = self._affinity.get(key, 0.0)  # type: ignore[arg-type]
            self._affinity[key] = min(1.0, current + normalized * 0.1)  # type: ignore[index]

    # ── Sleep check ──

    def check_sleep(self) -> None:
        """Transition idle agents to sleeping if past sleep_after hour."""
        import datetime

        hour = datetime.datetime.now().hour
        should_sleep = hour >= self._sleep_after or hour < 6

        for aid, state in self._states.items():
            if should_sleep and state.status == "idle":
                self._set(aid, "sleeping", "")
            elif not should_sleep and state.status == "sleeping":
                self._set(aid, "idle", "")

    # ── Listeners ──

    def add_listener(self, cb: Callable[[str, AgentState], None]) -> None:
        """Register a callback for state changes (used by WS gateway)."""
        self._listeners.append(cb)

    # ── Internal ──

    def _set(self, agent_id: str, status: str, detail: str) -> None:
        if agent_id not in self._states:
            self._states[agent_id] = AgentState()
        state = self._states[agent_id]
        if state.status == status and state.detail == detail:
            return  # no change
        state.status = status
        state.detail = detail
        state.since = time.time()
        for cb in self._listeners:
            cb(agent_id, state)
