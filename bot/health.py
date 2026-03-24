"""Health tracking: weight, sleep, exercise logging and stats."""

import json
import sqlite3
from datetime import datetime, timedelta

from bot.config import WORKSPACE_DIR
from bot.logger import get_logger

log = get_logger("health")

_DB_PATH = WORKSPACE_DIR / "health.db"
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH))
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.executescript("""
            CREATE TABLE IF NOT EXISTS health_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                type       TEXT NOT NULL,  -- weight, sleep, exercise
                data       TEXT NOT NULL,  -- JSON payload
                logged_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_health_type_date
                ON health_logs (type, logged_at);

            CREATE TABLE IF NOT EXISTS weight_goals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                start_weight REAL NOT NULL,
                target_weight REAL NOT NULL,
                start_date   TEXT NOT NULL,
                target_date  TEXT NOT NULL,
                created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
        """)
        _conn.commit()
    return _conn


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_weight(value: float, unit: str = "kg", date: str = "") -> str:
    conn = _get_conn()
    logged_at = date or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = json.dumps({"value": value, "unit": unit})
    conn.execute(
        "INSERT INTO health_logs (type, data, logged_at) VALUES (?, ?, ?)",
        ("weight", data, logged_at),
    )
    conn.commit()
    log.info("weight logged: %.1f %s at %s", value, unit, logged_at)
    return f"Logged weight: {value} {unit} ({logged_at})"


def log_sleep(hours: float, quality: str = "", bedtime: str = "",
              wake_time: str = "", date: str = "") -> str:
    conn = _get_conn()
    logged_at = date or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = json.dumps({
        "hours": hours,
        "quality": quality,
        "bedtime": bedtime,
        "wake_time": wake_time,
    })
    conn.execute(
        "INSERT INTO health_logs (type, data, logged_at) VALUES (?, ?, ?)",
        ("sleep", data, logged_at),
    )
    conn.commit()
    log.info("sleep logged: %.1f hrs at %s", hours, logged_at)
    return f"Logged sleep: {hours}h (quality: {quality or 'N/A'}) ({logged_at})"


def log_exercise(activity: str, duration_minutes: int, intensity: str = "moderate",
                 calories: int = 0, notes: str = "", date: str = "") -> str:
    conn = _get_conn()
    logged_at = date or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = json.dumps({
        "activity": activity,
        "duration_minutes": duration_minutes,
        "intensity": intensity,
        "calories": calories,
        "notes": notes,
    })
    conn.execute(
        "INSERT INTO health_logs (type, data, logged_at) VALUES (?, ?, ?)",
        ("exercise", data, logged_at),
    )
    conn.commit()
    tag = "moderate+" if intensity in ("moderate", "high", "vigorous") else "low"
    log.info("exercise logged: %s %dmin (%s) at %s", activity, duration_minutes, intensity, logged_at)
    return f"Logged exercise: {activity} {duration_minutes}min ({intensity}, {tag}) ({logged_at})"


# ---------------------------------------------------------------------------
# Weight goal
# ---------------------------------------------------------------------------

def set_weight_goal(start_weight: float, target_weight: float,
                    target_date: str) -> str:
    conn = _get_conn()
    now = datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO weight_goals (start_weight, target_weight, start_date, target_date) "
        "VALUES (?, ?, ?, ?)",
        (start_weight, target_weight, now, target_date),
    )
    conn.commit()
    diff = start_weight - target_weight
    return (
        f"Weight goal set: {start_weight} kg -> {target_weight} kg "
        f"(lose {diff:.1f} kg by {target_date})"
    )


# ---------------------------------------------------------------------------
# Stats / queries
# ---------------------------------------------------------------------------

def _week_bounds() -> tuple[str, str]:
    """Return (monday 00:00, sunday 23:59) of current week."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return (
        monday.strftime("%Y-%m-%d 00:00:00"),
        sunday.strftime("%Y-%m-%d 23:59:59"),
    )


def _query_logs(log_type: str, start: str, end: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT data, logged_at FROM health_logs "
        "WHERE type = ? AND logged_at BETWEEN ? AND ? "
        "ORDER BY logged_at",
        (log_type, start, end),
    ).fetchall()
    results = []
    for data_str, logged_at in rows:
        entry = json.loads(data_str)
        entry["logged_at"] = logged_at
        results.append(entry)
    return results


def weekly_exercise_stats() -> str:
    start, end = _week_bounds()
    entries = _query_logs("exercise", start, end)
    if not entries:
        return "This week: no exercise logged yet. Goal: 150 min moderate+ intensity."

    total_min = sum(e["duration_minutes"] for e in entries)
    moderate_plus = [e for e in entries if e.get("intensity", "") in ("moderate", "high", "vigorous")]
    mod_min = sum(e["duration_minutes"] for e in moderate_plus)
    total_cal = sum(e.get("calories", 0) for e in entries)

    goal = 150
    pct = min(mod_min / goal * 100, 100)
    remaining = max(goal - mod_min, 0)

    lines = [
        f"## This Week's Exercise ({start[:10]} ~ {end[:10]})",
        f"- Total sessions: {len(entries)}",
        f"- Total time: {total_min} min",
        f"- Moderate+ intensity: {mod_min} min / {goal} min goal ({pct:.0f}%)",
    ]
    if remaining > 0:
        lines.append(f"- Remaining: {remaining} min to hit weekly goal")
    else:
        lines.append(f"- Goal achieved! Exceeded by {mod_min - goal} min")
    if total_cal > 0:
        lines.append(f"- Estimated calories burned: {total_cal} kcal")

    lines.append("\nBreakdown:")
    for e in entries:
        lines.append(
            f"  - {e['logged_at'][:10]}: {e['activity']} "
            f"{e['duration_minutes']}min ({e.get('intensity', 'N/A')})"
        )
    return "\n".join(lines)


def weight_trend(days: int = 30) -> str:
    end = datetime.now().strftime("%Y-%m-%d 23:59:59")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    entries = _query_logs("weight", start, end)

    # Get active weight goal
    conn = _get_conn()
    goal_row = conn.execute(
        "SELECT start_weight, target_weight, start_date, target_date "
        "FROM weight_goals ORDER BY created_at DESC LIMIT 1"
    ).fetchone()

    if not entries:
        msg = f"No weight data in the last {days} days."
        if goal_row:
            msg += f"\nActive goal: {goal_row[0]} kg -> {goal_row[1]} kg by {goal_row[3]}"
        return msg

    lines = [f"## Weight Trend (last {days} days)"]

    first_val = entries[0]["value"]
    last_val = entries[-1]["value"]
    change = last_val - first_val
    direction = "down" if change < 0 else ("up" if change > 0 else "flat")
    lines.append(f"- Latest: {last_val} {entries[-1].get('unit', 'kg')}")
    lines.append(f"- Change: {change:+.1f} kg ({direction})")
    lines.append(f"- Entries: {len(entries)}")

    if goal_row:
        _, target, _, target_date = goal_row
        to_go = last_val - target
        lines.append(f"\nGoal: {target} kg by {target_date}")
        if to_go > 0:
            lines.append(f"  Still {to_go:.1f} kg to go")
        else:
            lines.append(f"  Goal reached! Currently {abs(to_go):.1f} kg below target")

    lines.append("\nRecent entries:")
    for e in entries[-10:]:  # show last 10
        lines.append(f"  - {e['logged_at'][:10]}: {e['value']} {e.get('unit', 'kg')}")

    return "\n".join(lines)


def sleep_summary(days: int = 7) -> str:
    end = datetime.now().strftime("%Y-%m-%d 23:59:59")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    entries = _query_logs("sleep", start, end)

    if not entries:
        return f"No sleep data in the last {days} days."

    hours_list = [e["hours"] for e in entries]
    avg = sum(hours_list) / len(hours_list)
    min_h = min(hours_list)
    max_h = max(hours_list)

    lines = [
        f"## Sleep Summary (last {days} days)",
        f"- Average: {avg:.1f} h/night",
        f"- Range: {min_h:.1f} - {max_h:.1f} h",
        f"- Entries: {len(entries)}",
    ]

    # Quality distribution
    qualities = [e.get("quality", "") for e in entries if e.get("quality")]
    if qualities:
        from collections import Counter
        dist = Counter(qualities)
        lines.append(f"- Quality: {', '.join(f'{k}={v}' for k, v in dist.most_common())}")

    lines.append("\nRecent:")
    for e in entries[-7:]:
        q = f" ({e['quality']})" if e.get("quality") else ""
        lines.append(f"  - {e['logged_at'][:10]}: {e['hours']}h{q}")

    return "\n".join(lines)


def health_overview() -> str:
    """Combined overview: exercise progress + weight trend + sleep."""
    parts = [
        weekly_exercise_stats(),
        "",
        weight_trend(days=30),
        "",
        sleep_summary(days=7),
    ]
    return "\n".join(parts)


def get_stats(stat_type: str, days: int = 30) -> str:
    if stat_type == "exercise" or stat_type == "weekly_exercise":
        return weekly_exercise_stats()
    if stat_type == "weight":
        return weight_trend(days=days)
    if stat_type == "sleep":
        return sleep_summary(days=days)
    if stat_type == "overview":
        return health_overview()
    return f"Unknown stat type: {stat_type}. Use: exercise, weight, sleep, overview."
