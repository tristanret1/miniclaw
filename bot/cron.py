"""Cron scheduler — SQLite-backed, asyncio-driven, with per-job context."""

import asyncio
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from croniter import croniter

from bot.config import (
    CRON_MAX_CONCURRENT,
    CRON_TIMEZONE,
    SYSTEM_PROMPT,
    WORKSPACE_DIR,
)
from bot.logger import get_logger

log = get_logger("cron")

DB_PATH = WORKSPACE_DIR / "cron.db"

# Timer bounds (seconds)
_MAX_TICK_INTERVAL = 60.0
_MIN_TICK_INTERVAL = 2.0

# Exponential backoff schedule for consecutive errors (seconds)
_BACKOFF = [30, 60, 300, 900, 3600]


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class CronJob:
    id: str
    name: str
    schedule_type: str          # "every" | "cron" | "at"
    schedule_value: str
    timezone: str
    payload: str
    channel_id: str
    enabled: bool
    created_at: str
    next_run_at: float          # Unix timestamp
    last_run_at: float | None
    last_status: str | None     # "ok" | "error"
    last_error: str | None
    consecutive_errors: int
    session_mode: str           # "isolated" | "persistent"
    context: str                # extra system instructions
    model: str                  # model override (empty = global)


# ── Schedule computation ─────────────────────────────────────────────────────

_DURATION_RE = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


def _parse_duration_seconds(value: str) -> float:
    """Parse duration string like '30m', '2h', '1d12h' into seconds."""
    m = _DURATION_RE.match(value.strip())
    if not m:
        raise ValueError(f"Invalid duration: {value!r}")
    days, hours, mins, secs = (int(g) if g else 0 for g in m.groups())
    total = days * 86400 + hours * 3600 + mins * 60 + secs
    if total <= 0:
        raise ValueError(f"Duration must be positive: {value!r}")
    return float(total)


def compute_next_run(
    schedule_type: str,
    schedule_value: str,
    timezone: str,
    after: float | None = None,
) -> float:
    """Compute the next run time as a Unix timestamp."""
    now = time.time()
    after = after or now

    if schedule_type == "every":
        interval = _parse_duration_seconds(schedule_value)
        return after + interval

    if schedule_type == "cron":
        tz = ZoneInfo(timezone)
        base_dt = datetime.fromtimestamp(after, tz=tz)
        cron = croniter(schedule_value, base_dt)
        next_dt = cron.get_next(datetime)
        return next_dt.timestamp()

    if schedule_type == "at":
        value = schedule_value.strip()
        if value.startswith("+"):
            offset = _parse_duration_seconds(value[1:])
            return now + offset
        tz = ZoneInfo(timezone)
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.timestamp()

    raise ValueError(f"Unknown schedule_type: {schedule_type!r}")


def _backoff_delay(consecutive_errors: int) -> float:
    """Get backoff delay in seconds for error count."""
    idx = min(consecutive_errors - 1, len(_BACKOFF) - 1)
    return _BACKOFF[max(idx, 0)]


# ── SQLite storage ───────────────────────────────────────────────────────────

def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            schedule_type TEXT NOT NULL,
            schedule_value TEXT NOT NULL,
            timezone TEXT NOT NULL DEFAULT 'America/Vancouver',
            payload TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            next_run_at REAL NOT NULL,
            last_run_at REAL,
            last_status TEXT,
            last_error TEXT,
            consecutive_errors INTEGER NOT NULL DEFAULT 0,
            session_mode TEXT NOT NULL DEFAULT 'isolated',
            context TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.commit()
    return conn


def _row_to_job(row: sqlite3.Row) -> CronJob:
    return CronJob(
        id=row["id"],
        name=row["name"],
        schedule_type=row["schedule_type"],
        schedule_value=row["schedule_value"],
        timezone=row["timezone"],
        payload=row["payload"],
        channel_id=row["channel_id"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        next_run_at=row["next_run_at"],
        last_run_at=row["last_run_at"],
        last_status=row["last_status"],
        last_error=row["last_error"],
        consecutive_errors=row["consecutive_errors"],
        session_mode=row["session_mode"],
        context=row["context"],
        model=row["model"],
    )


# ── Public CRUD (called from tools) ─────────────────────────────────────────

_db: sqlite3.Connection | None = None


def _get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = _init_db()
    return _db


def create_job(
    name: str,
    schedule_type: str,
    schedule_value: str,
    payload: str,
    channel_id: str,
    timezone: str = "",
    session_mode: str = "isolated",
    context: str = "",
    model: str = "",
) -> str:
    """Create a new cron job. Returns confirmation string."""
    tz = timezone or CRON_TIMEZONE
    if schedule_type not in ("every", "cron", "at"):
        return f"Error: invalid schedule_type '{schedule_type}'. Must be 'every', 'cron', or 'at'."

    try:
        next_run = compute_next_run(schedule_type, schedule_value, tz)
    except Exception as e:
        return f"Error: invalid schedule — {e}"

    if session_mode not in ("isolated", "persistent"):
        session_mode = "isolated"

    job_id = uuid.uuid4().hex[:12]
    now_iso = datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds")

    db = _get_db()
    db.execute(
        """INSERT INTO cron_jobs
           (id, name, schedule_type, schedule_value, timezone, payload, channel_id,
            enabled, created_at, next_run_at, consecutive_errors,
            session_mode, context, model)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 0, ?, ?, ?)""",
        (job_id, name, schedule_type, schedule_value, tz, payload, channel_id,
         now_iso, next_run, session_mode, context, model),
    )
    db.commit()

    next_dt = datetime.fromtimestamp(next_run, ZoneInfo(tz))
    log.info("created cron job: %s (%s) next=%s", name, job_id, next_dt.isoformat())

    # Re-arm scheduler if running
    if _scheduler and _scheduler._running:
        _scheduler._arm_timer()

    return (
        f"Created job '{name}' (id={job_id})\n"
        f"Schedule: {schedule_type} {schedule_value}\n"
        f"Session: {session_mode}\n"
        f"Next run: {next_dt.strftime('%Y-%m-%d %H:%M %Z')}"
    )


def list_jobs(include_disabled: bool = False) -> str:
    """List cron jobs. Returns formatted string."""
    db = _get_db()
    if include_disabled:
        rows = db.execute("SELECT * FROM cron_jobs ORDER BY next_run_at").fetchall()
    else:
        rows = db.execute("SELECT * FROM cron_jobs WHERE enabled=1 ORDER BY next_run_at").fetchall()

    if not rows:
        return "No scheduled jobs."

    lines = []
    for row in rows:
        job = _row_to_job(row)
        tz = ZoneInfo(job.timezone)
        next_dt = datetime.fromtimestamp(job.next_run_at, tz).strftime("%Y-%m-%d %H:%M %Z")
        status = job.last_status or "never run"
        enabled = "" if job.enabled else " [DISABLED]"
        mode = f" [{job.session_mode}]" if job.session_mode != "isolated" else ""
        model_info = f" model={job.model}" if job.model else ""
        lines.append(
            f"• **{job.name}** (id={job.id}){enabled}{mode}{model_info}\n"
            f"  {job.schedule_type} {job.schedule_value} | next: {next_dt} | last: {status}"
        )
        if job.last_error:
            lines.append(f"  error: {job.last_error[:100]}")

    return "\n".join(lines)


def delete_job(job_id: str) -> str:
    """Delete a job by ID or name. Returns confirmation."""
    db = _get_db()

    row = db.execute("SELECT id, name FROM cron_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        row = db.execute("SELECT id, name FROM cron_jobs WHERE name=?", (job_id,)).fetchone()
    if not row:
        return f"No job found with ID or name '{job_id}'."

    db.execute("DELETE FROM cron_jobs WHERE id=?", (row["id"],))
    db.commit()
    log.info("deleted cron job: %s (%s)", row["name"], row["id"])

    if _scheduler and _scheduler._running:
        _scheduler._arm_timer()

    return f"Deleted job '{row['name']}' (id={row['id']})."


# ── Scheduler ────────────────────────────────────────────────────────────────

class CronScheduler:
    """asyncio-based cron scheduler with concurrent execution."""

    def __init__(self):
        self._bot = None
        self._timer_handle: asyncio.TimerHandle | None = None
        self._running = False
        self._ticking = False
        self._sem: asyncio.Semaphore | None = None

    async def start(self, bot) -> None:
        """Start the scheduler. Call from on_ready()."""
        self._bot = bot
        self._running = True
        self._sem = asyncio.Semaphore(CRON_MAX_CONCURRENT)

        _get_db()

        self._catchup_missed()
        self._arm_timer()
        count = _get_db().execute("SELECT COUNT(*) FROM cron_jobs WHERE enabled=1").fetchone()[0]
        log.info("cron scheduler started (%d enabled jobs)", count)

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._timer_handle:
            self._timer_handle.cancel()
            self._timer_handle = None
        log.info("cron scheduler stopped")

    def _catchup_missed(self) -> None:
        """Advance next_run_at for recurring jobs that are past due."""
        db = _get_db()
        now = time.time()
        rows = db.execute(
            "SELECT * FROM cron_jobs WHERE enabled=1 AND next_run_at < ?", (now,)
        ).fetchall()

        for row in rows:
            job = _row_to_job(row)
            if job.schedule_type == "at":
                continue  # one-shot: let it fire on next tick
            try:
                next_run = job.next_run_at
                while next_run <= now:
                    next_run = compute_next_run(job.schedule_type, job.schedule_value, job.timezone, next_run)
                db.execute("UPDATE cron_jobs SET next_run_at=? WHERE id=?", (next_run, job.id))
                log.info("catchup: advanced %s to %s", job.name,
                         datetime.fromtimestamp(next_run, ZoneInfo(job.timezone)).isoformat())
            except Exception as e:
                log.error("catchup failed for %s: %s", job.name, e)

        db.commit()

    def _arm_timer(self) -> None:
        """Schedule the next timer tick."""
        if not self._running:
            return

        if self._timer_handle:
            self._timer_handle.cancel()

        db = _get_db()
        row = db.execute(
            "SELECT MIN(next_run_at) as min_next FROM cron_jobs WHERE enabled=1"
        ).fetchone()

        if row and row["min_next"] is not None:
            delay = max(row["min_next"] - time.time(), 0)
            delay = min(delay, _MAX_TICK_INTERVAL)
            delay = max(delay, _MIN_TICK_INTERVAL)
        else:
            delay = _MAX_TICK_INTERVAL

        loop = asyncio.get_event_loop()
        self._timer_handle = loop.call_later(delay, lambda: asyncio.create_task(self._on_tick()))

    async def _on_tick(self) -> None:
        """Timer callback: find and execute due jobs concurrently."""
        if not self._running:
            return
        if self._ticking:
            self._arm_timer()
            return

        self._ticking = True
        try:
            db = _get_db()
            now = time.time()
            rows = db.execute(
                "SELECT * FROM cron_jobs WHERE enabled=1 AND next_run_at <= ?", (now,)
            ).fetchall()

            if rows:
                jobs = [_row_to_job(row) for row in rows]
                log.info("cron tick: %d due job(s) — %s", len(jobs),
                         ", ".join(j.name for j in jobs))

                results = await asyncio.gather(
                    *[self._execute_job(job) for job in jobs],
                    return_exceptions=True,
                )

                for job, result in zip(jobs, results):
                    self._apply_result(job, result)

        except Exception as e:
            log.error("cron tick error: %s", e)
        finally:
            self._ticking = False
            self._arm_timer()

    async def _execute_job(self, job: CronJob) -> str:
        """Execute a single job within semaphore. Returns reply text."""
        async with self._sem:
            log.info("executing job: %s (%s) mode=%s", job.name, job.id, job.session_mode)

            # Build per-job system prompt
            system_prompt = SYSTEM_PROMPT
            task_header = f"\n\n---\n\n[Scheduled Task: {job.name}]"
            if job.context:
                system_prompt += task_header + "\n" + job.context
            else:
                system_prompt += task_header

            # Use session key for persistent mode, or isolated
            if job.session_mode == "persistent":
                session_key = f"cron:{job.id}"
            else:
                session_key = f"cron:{job.id}:{int(time.time())}"

            # Use the unified LLM entry point
            from bot import llm
            reply = await llm.reply(session_key, job.payload)

            # Deliver to Discord
            if self._bot and reply.strip():
                try:
                    channel = self._bot.get_channel(int(job.channel_id))
                    if channel is None:
                        channel = await self._bot.fetch_channel(int(job.channel_id))
                    for i in range(0, len(reply), 2000):
                        await channel.send(reply[i : i + 2000])
                    log.info("job %s delivered to channel %s (%d chars)", job.name, job.channel_id, len(reply))
                except Exception as e:
                    log.error("job %s delivery failed: %s", job.name, e)
                    raise

            return reply

    def _apply_result(self, job: CronJob, result: str | BaseException) -> None:
        """Update job state after execution."""
        db = _get_db()
        now = time.time()

        if isinstance(result, BaseException):
            error_msg = str(result)[:500]
            consec = job.consecutive_errors + 1
            log.error("job %s failed (errors=%d): %s", job.name, consec, error_msg)

            try:
                if job.schedule_type == "at":
                    db.execute(
                        "UPDATE cron_jobs SET last_run_at=?, last_status='error', last_error=?, "
                        "consecutive_errors=?, enabled=0 WHERE id=?",
                        (now, error_msg, consec, job.id),
                    )
                else:
                    natural_next = compute_next_run(job.schedule_type, job.schedule_value, job.timezone, now)
                    backoff_next = now + _backoff_delay(consec)
                    next_run = max(natural_next, backoff_next)
                    db.execute(
                        "UPDATE cron_jobs SET last_run_at=?, last_status='error', last_error=?, "
                        "consecutive_errors=?, next_run_at=? WHERE id=?",
                        (now, error_msg, consec, next_run, job.id),
                    )
            except Exception as e:
                log.error("failed to update job %s after error: %s", job.name, e)
        else:
            log.info("job %s completed successfully", job.name)
            try:
                if job.schedule_type == "at":
                    db.execute(
                        "UPDATE cron_jobs SET last_run_at=?, last_status='ok', last_error=NULL, "
                        "consecutive_errors=0, enabled=0 WHERE id=?",
                        (now, job.id),
                    )
                else:
                    next_run = compute_next_run(job.schedule_type, job.schedule_value, job.timezone, now)
                    db.execute(
                        "UPDATE cron_jobs SET last_run_at=?, last_status='ok', last_error=NULL, "
                        "consecutive_errors=0, next_run_at=? WHERE id=?",
                        (now, next_run, job.id),
                    )
            except Exception as e:
                log.error("failed to update job %s after success: %s", job.name, e)

        db.commit()


# Module-level singleton
_scheduler: CronScheduler | None = None


def get_scheduler() -> CronScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler
