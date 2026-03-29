"""Tests for AgentStatusTracker."""

import sys
from pathlib import Path

# Add src/ to import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from status import AgentStatusTracker, AgentState


def test_initial_state_is_offline():
    tracker = AgentStatusTracker(["a1", "a2"])
    s = tracker.get_status("a1")
    assert s["status"] == "offline"
    assert s["detail"] == ""


def test_on_working_sets_status():
    tracker = AgentStatusTracker(["a1"])
    tracker.on_working("a1", "Processing message")
    s = tracker.get_status("a1")
    assert s["status"] == "working"
    assert s["detail"] == "Processing message"


def test_on_idle_clears_detail():
    tracker = AgentStatusTracker(["a1"])
    tracker.on_working("a1", "busy")
    tracker.on_idle("a1")
    s = tracker.get_status("a1")
    assert s["status"] == "idle"
    assert s["detail"] == ""


def test_on_offline():
    tracker = AgentStatusTracker(["a1"])
    tracker.on_idle("a1")
    tracker.on_offline("a1")
    assert tracker.get_status("a1")["status"] == "offline"


def test_on_online():
    tracker = AgentStatusTracker(["a1"])
    tracker.on_online("a1")
    assert tracker.get_status("a1")["status"] == "idle"


def test_get_all_statuses():
    tracker = AgentStatusTracker(["a1", "a2"])
    tracker.on_working("a1", "job")
    all_s = tracker.get_all_statuses()
    assert "a1" in all_s
    assert "a2" in all_s
    assert all_s["a1"]["status"] == "working"
    assert all_s["a2"]["status"] == "offline"


def test_unknown_agent_returns_default():
    tracker = AgentStatusTracker([])
    s = tracker.get_status("nonexistent")
    assert s["status"] == "offline"


def test_no_change_does_not_notify():
    tracker = AgentStatusTracker(["a1"])
    calls = []
    tracker.add_listener(lambda aid, state: calls.append((aid, state.status)))
    tracker.on_idle("a1")
    tracker.on_idle("a1")  # same status, should not fire again
    assert len(calls) == 1


def test_listener_fires_on_change():
    tracker = AgentStatusTracker(["a1"])
    calls = []
    tracker.add_listener(lambda aid, state: calls.append((aid, state.status)))
    tracker.on_working("a1", "test")
    tracker.on_idle("a1")
    assert calls == [("a1", "working"), ("a1", "idle")]


def test_affinity_default_zero():
    tracker = AgentStatusTracker(["a1", "a2"])
    assert tracker.get_affinity("a1", "a2") == 0.0


def test_compute_affinity():
    tracker = AgentStatusTracker(["a1", "a2"])
    tracker.compute_affinity({("a1", "a2"): 10})
    score = tracker.get_affinity("a1", "a2")
    assert 0 < score <= 1.0


def test_get_all_affinities():
    tracker = AgentStatusTracker(["a1", "a2"])
    tracker.compute_affinity({("a1", "a2"): 10})
    affinities = tracker.get_all_affinities()
    assert len(affinities) == 1
    assert affinities[0]["score"] > 0


def test_affinity_decay():
    tracker = AgentStatusTracker(["a1", "a2"])
    tracker.compute_affinity({("a1", "a2"): 10})
    score1 = tracker.get_affinity("a1", "a2")
    # Recompute with zero interactions — should decay
    tracker.compute_affinity({}, decay=0.5)
    score2 = tracker.get_affinity("a1", "a2")
    assert score2 < score1


def test_dynamic_agent_creation():
    """Calling on_working for unknown agent_id creates it."""
    tracker = AgentStatusTracker([])
    tracker.on_working("new_agent", "hello")
    s = tracker.get_status("new_agent")
    assert s["status"] == "working"
