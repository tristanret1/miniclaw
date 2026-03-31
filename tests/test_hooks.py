"""Tests for bot.hooks — agent lifecycle hook registry."""

import pytest

from bot import hooks


@pytest.fixture(autouse=True)
def _clean_hooks():
    """Reset hooks between tests."""
    from bot.hooks import _reset
    _reset()
    yield
    _reset()


def test_fire_working_calls_registered_callbacks():
    calls = []
    hooks.register_on_working(lambda aid, detail: calls.append((aid, detail)))
    hooks.fire_working("agent-1", "busy")
    assert calls == [("agent-1", "busy")]


def test_fire_idle_calls_registered_callbacks():
    calls = []
    hooks.register_on_idle(lambda aid: calls.append(aid))
    hooks.fire_idle("agent-1")
    assert calls == ["agent-1"]


def test_fire_working_ignores_callback_errors():
    def bad_cb(aid, detail):
        raise RuntimeError("boom")
    hooks.register_on_working(bad_cb)
    # Should not raise
    hooks.fire_working("agent-1", "test")


def test_fire_idle_ignores_callback_errors():
    def bad_cb(aid):
        raise RuntimeError("boom")
    hooks.register_on_idle(bad_cb)
    hooks.fire_idle("agent-1")


def test_multiple_callbacks_all_called():
    calls_a, calls_b = [], []
    hooks.register_on_working(lambda aid, d: calls_a.append(aid))
    hooks.register_on_working(lambda aid, d: calls_b.append(aid))
    hooks.fire_working("x", "")
    assert len(calls_a) == 1
    assert len(calls_b) == 1
