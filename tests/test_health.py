"""Tests for bot.health module."""

import json
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from bot import health


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Each test gets a fresh SQLite database."""
    db_path = tmp_path / "health.db"
    monkeypatch.setattr(health, "_DB_PATH", db_path)
    health._conn = None  # force re-init
    yield
    if health._conn:
        health._conn.close()
        health._conn = None


# ---------------------------------------------------------------------------
# Logging tests
# ---------------------------------------------------------------------------

class TestLogWeight:
    def test_basic(self):
        result = health.log_weight(75.5)
        assert "75.5" in result
        assert "kg" in result

    def test_custom_unit_and_date(self):
        result = health.log_weight(166.0, unit="lb", date="2026-03-20")
        assert "166.0" in result
        assert "lb" in result
        assert "2026-03-20" in result

    def test_persists_to_db(self):
        health.log_weight(80.0)
        conn = health._get_conn()
        row = conn.execute("SELECT data FROM health_logs WHERE type='weight'").fetchone()
        assert row is not None
        data = json.loads(row[0])
        assert data["value"] == 80.0


class TestLogSleep:
    def test_basic(self):
        result = health.log_sleep(7.5, quality="good")
        assert "7.5" in result
        assert "good" in result

    def test_with_times(self):
        result = health.log_sleep(8.0, bedtime="23:00", wake_time="07:00")
        assert "8.0" in result

    def test_persists(self):
        health.log_sleep(6.5, quality="fair", bedtime="00:30", wake_time="07:00")
        conn = health._get_conn()
        row = conn.execute("SELECT data FROM health_logs WHERE type='sleep'").fetchone()
        data = json.loads(row[0])
        assert data["hours"] == 6.5
        assert data["quality"] == "fair"


class TestLogExercise:
    def test_basic(self):
        result = health.log_exercise("running", 30, intensity="high")
        assert "running" in result
        assert "30" in result
        assert "high" in result

    def test_moderate_plus_tag(self):
        result = health.log_exercise("cycling", 45, intensity="moderate")
        assert "moderate+" in result

    def test_low_intensity(self):
        result = health.log_exercise("walking", 20, intensity="low")
        assert "low" in result.lower()

    def test_with_calories(self):
        health.log_exercise("HIIT", 25, intensity="vigorous", calories=350)
        conn = health._get_conn()
        row = conn.execute("SELECT data FROM health_logs WHERE type='exercise'").fetchone()
        data = json.loads(row[0])
        assert data["calories"] == 350
        assert data["intensity"] == "vigorous"


# ---------------------------------------------------------------------------
# Weight goal
# ---------------------------------------------------------------------------

class TestWeightGoal:
    def test_set_goal(self):
        result = health.set_weight_goal(80.0, 72.0, "2026-06-01")
        assert "80.0" in result
        assert "72.0" in result
        assert "8.0" in result  # lose amount

    def test_goal_persists(self):
        health.set_weight_goal(85.0, 75.0, "2026-12-31")
        conn = health._get_conn()
        row = conn.execute("SELECT target_weight, target_date FROM weight_goals").fetchone()
        assert row[0] == 75.0
        assert row[1] == "2026-12-31"


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestWeeklyExercise:
    def test_no_data(self):
        result = health.weekly_exercise_stats()
        assert "no exercise" in result.lower()
        assert "150" in result

    def test_with_data(self):
        today = datetime.now().strftime("%Y-%m-%d 12:00:00")
        health.log_exercise("running", 40, intensity="high", date=today)
        health.log_exercise("yoga", 30, intensity="moderate", date=today)
        health.log_exercise("walking", 20, intensity="low", date=today)

        result = health.weekly_exercise_stats()
        assert "70 min / 150 min" in result  # 40+30 moderate+
        assert "80 min" in result.replace("80,", "80")  # remaining


    def test_goal_achieved(self):
        today = datetime.now().strftime("%Y-%m-%d 10:00:00")
        health.log_exercise("running", 80, intensity="high", date=today)
        health.log_exercise("cycling", 80, intensity="moderate", date=today)

        result = health.weekly_exercise_stats()
        assert "achieved" in result.lower() or "exceeded" in result.lower()


class TestWeightTrend:
    def test_no_data(self):
        result = health.weight_trend()
        assert "no weight data" in result.lower()

    def test_with_data(self):
        health.log_weight(80.0, date="2026-03-10 08:00:00")
        health.log_weight(79.5, date="2026-03-15 08:00:00")
        health.log_weight(79.0, date="2026-03-20 08:00:00")

        result = health.weight_trend(days=30)
        assert "79.0" in result  # latest
        assert "-1.0" in result  # change

    def test_with_goal(self):
        health.set_weight_goal(80.0, 72.0, "2026-06-01")
        health.log_weight(78.0, date=datetime.now().strftime("%Y-%m-%d 08:00:00"))

        result = health.weight_trend()
        assert "72.0" in result or "72" in result
        assert "6.0" in result  # to go


class TestSleepSummary:
    def test_no_data(self):
        result = health.sleep_summary()
        assert "no sleep data" in result.lower()

    def test_with_data(self):
        for i in range(5):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d 08:00:00")
            health.log_sleep(7.0 + i * 0.2, quality="good", date=date)

        result = health.sleep_summary(days=7)
        assert "average" in result.lower()
        assert "good" in result


class TestHealthOverview:
    def test_overview_combines_all(self):
        result = health.health_overview()
        # Should contain sections for all three
        assert "exercise" in result.lower() or "no exercise" in result.lower()
        assert "weight" in result.lower() or "no weight" in result.lower()
        assert "sleep" in result.lower() or "no sleep" in result.lower()


class TestGetStats:
    def test_exercise(self):
        result = health.get_stats("exercise")
        assert "150" in result or "exercise" in result.lower()

    def test_unknown(self):
        result = health.get_stats("unknown_type")
        assert "unknown" in result.lower()
