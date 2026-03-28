"""Cron scheduler — SQLite/PostgreSQL backed, asyncio-driven, with per-job context."""

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
from bot.db import use_postgres
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
    delivery_channel: str       # "discord" | "sms"


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
            model TEXT NOT NULL DEFAULT '',
            delivery_channel TEXT NOT NULL DEFAULT 'discord'
        )
    """)
    conn.commit()

    # Migration: add delivery_channel if missing (existing DBs)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(cron_jobs)").fetchall()}
    if "delivery_channel" not in cols:
        conn.execute("ALTER TABLE cron_jobs ADD COLUMN delivery_channel TEXT NOT NULL DEFAULT 'discord'")
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
        delivery_channel=row["delivery_channel"] if "delivery_channel" in row.keys() else "discord",
    )


def _record_to_job(r) -> CronJob:
    """Convert an asyncpg Record to CronJob."""
    return CronJob(
        id=r["id"],
        name=r["name"],
        schedule_type=r["schedule_type"],
        schedule_value=r["schedule_value"],
        timezone=r["timezone"],
        payload=r["payload"],
        channel_id=r["channel_id"],
        enabled=bool(r["enabled"]),
        created_at=str(r["created_at"]),
        next_run_at=r["next_run_at"],
        last_run_at=r["last_run_at"],
        last_status=r["last_status"],
        last_error=r["last_error"],
        consecutive_errors=r["consecutive_errors"],
        session_mode=r["session_mode"],
        context=r["context"],
        model=r["model"],
        delivery_channel=r["delivery_channel"],
    )


# ── Public CRUD (called from tools) ─────────────────────────────────────────

_db: sqlite3.Connection | None = None


def _get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = _init_db()
    return _db


async def create_job(
    name: str,
    schedule_type: str,
    schedule_value: str,
    payload: str,
    channel_id: str,
    timezone: str = "",
    session_mode: str = "isolated",
    context: str = "",
    model: str = "",
    delivery_channel: str = "discord",
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

    if delivery_channel not in ("discord", "sms", "imessage"):
        delivery_channel = "discord"

    job_id = uuid.uuid4().hex[:12]
    now_dt = datetime.now(ZoneInfo(tz))

    if use_postgres():
        from bot.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO cron_jobs
                   (id, name, schedule_type, schedule_value, timezone, payload, channel_id,
                    enabled, created_at, next_run_at, consecutive_errors,
                    session_mode, context, model, delivery_channel)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, true, $8, $9, 0, $10, $11, $12, $13)""",
                job_id, name, schedule_type, schedule_value, tz, payload, channel_id,
                now_dt, next_run, session_mode, context, model, delivery_channel,
            )
    else:
        now_iso = now_dt.isoformat(timespec="seconds")
        db = _get_db()
        db.execute(
            """INSERT INTO cron_jobs
               (id, name, schedule_type, schedule_value, timezone, payload, channel_id,
                enabled, created_at, next_run_at, consecutive_errors,
                session_mode, context, model, delivery_channel)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 0, ?, ?, ?, ?)""",
            (job_id, name, schedule_type, schedule_value, tz, payload, channel_id,
             now_iso, next_run, session_mode, context, model, delivery_channel),
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


async def list_jobs(include_disabled: bool = False) -> str:
    """List cron jobs. Returns formatted string."""
    if use_postgres():
        from bot.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            if include_disabled:
                rows = await conn.fetch("SELECT * FROM cron_jobs ORDER BY next_run_at")
            else:
                rows = await conn.fetch("SELECT * FROM cron_jobs WHERE enabled=true ORDER BY next_run_at")
        jobs = [_record_to_job(r) for r in rows]
    else:
        db = _get_db()
        if include_disabled:
            rows = db.execute("SELECT * FROM cron_jobs ORDER BY next_run_at").fetchall()
        else:
            rows = db.execute("SELECT * FROM cron_jobs WHERE enabled=1 ORDER BY next_run_at").fetchall()
        jobs = [_row_to_job(r) for r in rows]

    if not jobs:
        return "No scheduled jobs."

    lines = []
    for job in jobs:
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


async def delete_job(job_id: str) -> str:
    """Delete a job by ID or name. Returns confirmation."""
    if use_postgres():
        from bot.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id, name FROM cron_jobs WHERE id=$1", job_id)
            if not row:
                row = await conn.fetchrow("SELECT id, name FROM cron_jobs WHERE name=$1", job_id)
            if not row:
                return f"No job found with ID or name '{job_id}'."
            await conn.execute("DELETE FROM cron_jobs WHERE id=$1", row["id"])
    else:
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

        if use_postgres():
            from bot.db import get_pool
            pool = await get_pool()
            await self._pg_catchup_missed(pool)
            await self._pg_arm_timer(pool)
            count = await pool.fetchval("SELECT COUNT(*) FROM cron_jobs WHERE enabled=true")
        else:
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
            if use_postgres():
                from bot.db import get_pool
                pool = await get_pool()
                await self._pg_arm_timer(pool)
            else:
                self._arm_timer()
            return

        self._ticking = True
        try:
            now = time.time()

            if use_postgres():
                from bot.db import get_pool
                pool = await get_pool()
                rows = await pool.fetch(
                    "SELECT * FROM cron_jobs WHERE enabled=true AND next_run_at <= $1", now,
                )
                jobs = [_record_to_job(r) for r in rows] if rows else []
            else:
                db = _get_db()
                rows = db.execute(
                    "SELECT * FROM cron_jobs WHERE enabled=1 AND next_run_at <= ?", (now,)
                ).fetchall()
                jobs = [_row_to_job(row) for row in rows] if rows else []

            if jobs:
                log.info("cron tick: %d due job(s) — %s", len(jobs),
                         ", ".join(j.name for j in jobs))

                results = await asyncio.gather(
                    *[self._execute_job(job) for job in jobs],
                    return_exceptions=True,
                )

                for job, result in zip(jobs, results):
                    await self._apply_result_async(job, result)

        except Exception as e:
            log.error("cron tick error: %s", e)
        finally:
            self._ticking = False
            if use_postgres():
                from bot.db import get_pool
                pool = await get_pool()
                await self._pg_arm_timer(pool)
            else:
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

            # Deliver result
            if reply.strip():
                if job.delivery_channel == "sms":
                    try:
                        from bot.tools import run_sms
                        result = await run_sms(to=job.channel_id, message=reply)
                        log.info("job %s delivered via SMS to %s: %s", job.name, job.channel_id, result)
                    except Exception as e:
                        log.error("job %s SMS delivery failed: %s", job.name, e)
                        raise
                elif job.delivery_channel == "imessage":
                    try:
                        from bot.gateway.imessage import get_gateway_client, send_imessage, run_imessage_send
                        client = get_gateway_client()
                        if client:
                            result = await send_imessage(client, to=job.channel_id, message=reply)
                        else:
                            result = await run_imessage_send(to=job.channel_id, message=reply)
                        log.info("job %s delivered via iMessage to %s: %s", job.name, job.channel_id, result)
                    except Exception as e:
                        log.error("job %s iMessage delivery failed: %s", job.name, e)
                        raise
                elif self._bot:
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

    async def _apply_result_async(self, job: CronJob, result: str | BaseException) -> None:
        """Update job state after execution (both backends)."""
        now = time.time()

        if isinstance(result, BaseException):
            error_msg = str(result)[:500]
            consec = job.consecutive_errors + 1
            log.error("job %s failed (errors=%d): %s", job.name, consec, error_msg)

            try:
                if job.schedule_type == "at":
                    await self._update_job_state(
                        job.id, last_run_at=now, last_status="error",
                        last_error=error_msg, consecutive_errors=consec, enabled=False,
                    )
                else:
                    natural_next = compute_next_run(job.schedule_type, job.schedule_value, job.timezone, now)
                    backoff_next = now + _backoff_delay(consec)
                    next_run = max(natural_next, backoff_next)
                    await self._update_job_state(
                        job.id, last_run_at=now, last_status="error",
                        last_error=error_msg, consecutive_errors=consec, next_run_at=next_run,
                    )
            except Exception as e:
                log.error("failed to update job %s after error: %s", job.name, e)
        else:
            log.info("job %s completed successfully", job.name)
            try:
                if job.schedule_type == "at":
                    await self._update_job_state(
                        job.id, last_run_at=now, last_status="ok",
                        last_error=None, consecutive_errors=0, enabled=False,
                    )
                else:
                    next_run = compute_next_run(job.schedule_type, job.schedule_value, job.timezone, now)
                    await self._update_job_state(
                        job.id, last_run_at=now, last_status="ok",
                        last_error=None, consecutive_errors=0, next_run_at=next_run,
                    )
            except Exception as e:
                log.error("failed to update job %s after success: %s", job.name, e)

    async def _update_job_state(self, job_id: str, *, last_run_at: float,
                                last_status: str, last_error: str | None,
                                consecutive_errors: int,
                                enabled: bool | None = None,
                                next_run_at: float | None = None) -> None:
        """Update job state in the active backend."""
        if use_postgres():
            from bot.db import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                if enabled is not None and not enabled:
                    # Disable (one-shot "at" jobs)
                    await conn.execute(
                        "UPDATE cron_jobs SET last_run_at=$1, last_status=$2, last_error=$3, "
                        "consecutive_errors=$4, enabled=false WHERE id=$5",
                        last_run_at, last_status, last_error, consecutive_errors, job_id,
                    )
                elif next_run_at is not None:
                    await conn.execute(
                        "UPDATE cron_jobs SET last_run_at=$1, last_status=$2, last_error=$3, "
                        "consecutive_errors=$4, next_run_at=$5 WHERE id=$6",
                        last_run_at, last_status, last_error, consecutive_errors, next_run_at, job_id,
                    )
        else:
            db = _get_db()
            if enabled is not None and not enabled:
                db.execute(
                    "UPDATE cron_jobs SET last_run_at=?, last_status=?, last_error=?, "
                    "consecutive_errors=?, enabled=0 WHERE id=?",
                    (last_run_at, last_status, last_error, consecutive_errors, job_id),
                )
            elif next_run_at is not None:
                db.execute(
                    "UPDATE cron_jobs SET last_run_at=?, last_status=?, last_error=?, "
                    "consecutive_errors=?, next_run_at=? WHERE id=?",
                    (last_run_at, last_status, last_error, consecutive_errors, next_run_at, job_id),
                )
            db.commit()

    # ── PostgreSQL scheduler helpers ──────────────────────────────────────────

    async def _pg_catchup_missed(self, pool) -> None:
        """Advance next_run_at for recurring jobs past due (PostgreSQL)."""
        now = time.time()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM cron_jobs WHERE enabled=true AND next_run_at < $1", now,
            )
            for r in rows:
                job = _record_to_job(r)
                if job.schedule_type == "at":
                    continue
                try:
                    next_run = job.next_run_at
                    while next_run <= now:
                        next_run = compute_next_run(job.schedule_type, job.schedule_value, job.timezone, next_run)
                    await conn.execute("UPDATE cron_jobs SET next_run_at=$1 WHERE id=$2", next_run, job.id)
                    log.info("catchup: advanced %s to %s", job.name,
                             datetime.fromtimestamp(next_run, ZoneInfo(job.timezone)).isoformat())
                except Exception as e:
                    log.error("catchup failed for %s: %s", job.name, e)

    async def _pg_arm_timer(self, pool) -> None:
        """Schedule the next timer tick (PostgreSQL)."""
        if not self._running:
            return
        if self._timer_handle:
            self._timer_handle.cancel()

        row = await pool.fetchrow(
            "SELECT MIN(next_run_at) as min_next FROM cron_jobs WHERE enabled=true"
        )
        if row and row["min_next"] is not None:
            delay = max(row["min_next"] - time.time(), 0)
            delay = min(delay, _MAX_TICK_INTERVAL)
            delay = max(delay, _MIN_TICK_INTERVAL)
        else:
            delay = _MAX_TICK_INTERVAL

        loop = asyncio.get_event_loop()
        self._timer_handle = loop.call_later(delay, lambda: asyncio.create_task(self._on_tick()))


# Module-level singleton
_scheduler: CronScheduler | None = None


def get_scheduler() -> CronScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler
