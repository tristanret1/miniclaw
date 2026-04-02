"""Cron scheduler — PostgreSQL backed, asyncio-driven, with per-job context."""

import asyncio
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter

from bot.config import (
    get_config,
    get_system_prompt,
)
from bot.storage.db import get_pool
from bot.utils.discord import send_chunks
from bot.utils.session_keys import cron_key
from bot.logger import get_logger

log = get_logger("cron")

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
    tz = timezone or get_config().services.cron.timezone
    if schedule_type not in ("every", "cron", "at"):
        return f"Error: invalid schedule_type '{schedule_type}'. Must be 'every', 'cron', or 'at'."

    try:
        next_run = compute_next_run(schedule_type, schedule_value, tz)
    except Exception as e:
        return f"Error: invalid schedule — {e}"

    if session_mode not in ("isolated", "persistent"):
        session_mode = "isolated"

    if delivery_channel not in ("discord", "sms", "imessage", "feishu"):
        delivery_channel = "discord"

    job_id = uuid.uuid4().hex[:12]
    now_dt = datetime.now(ZoneInfo(tz))

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

    next_dt = datetime.fromtimestamp(next_run, ZoneInfo(tz))
    log.info("created cron job: %s (%s) next=%s", name, job_id, next_dt.isoformat())

    # Re-arm scheduler if running
    if _scheduler and _scheduler._running:
        await _scheduler._arm_timer()

    return (
        f"Created job '{name}' (id={job_id})\n"
        f"Schedule: {schedule_type} {schedule_value}\n"
        f"Session: {session_mode}\n"
        f"Next run: {next_dt.strftime('%Y-%m-%d %H:%M %Z')}"
    )


async def list_jobs(include_disabled: bool = False) -> str:
    """List cron jobs. Returns formatted string."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if include_disabled:
            rows = await conn.fetch("SELECT * FROM cron_jobs ORDER BY next_run_at")
        else:
            rows = await conn.fetch("SELECT * FROM cron_jobs WHERE enabled=true ORDER BY next_run_at")
    jobs = [_record_to_job(r) for r in rows]

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
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, name FROM cron_jobs WHERE id=$1", job_id)
        if not row:
            row = await conn.fetchrow("SELECT id, name FROM cron_jobs WHERE name=$1", job_id)
        if not row:
            return f"No job found with ID or name '{job_id}'."
        await conn.execute("DELETE FROM cron_jobs WHERE id=$1", row["id"])

    log.info("deleted cron job: %s (%s)", row["name"], row["id"])

    if _scheduler and _scheduler._running:
        await _scheduler._arm_timer()

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
        self._sem = asyncio.Semaphore(get_config().services.cron.max_concurrent)

        pool = await get_pool()
        await self._catchup_missed(pool)
        await self._arm_timer()
        count = await pool.fetchval("SELECT COUNT(*) FROM cron_jobs WHERE enabled=true")

        log.info("cron scheduler started (%d enabled jobs)", count)

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._timer_handle:
            self._timer_handle.cancel()
            self._timer_handle = None
        log.info("cron scheduler stopped")

    async def _catchup_missed(self, pool) -> None:
        """Advance next_run_at for recurring jobs past due."""
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

    async def _arm_timer(self) -> None:
        """Schedule the next timer tick."""
        if not self._running:
            return
        if self._timer_handle:
            self._timer_handle.cancel()

        pool = await get_pool()
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

    async def _on_tick(self) -> None:
        """Timer callback: find and execute due jobs concurrently."""
        if not self._running:
            return
        if self._ticking:
            await self._arm_timer()
            return

        self._ticking = True
        try:
            now = time.time()
            pool = await get_pool()
            rows = await pool.fetch(
                "SELECT * FROM cron_jobs WHERE enabled=true AND next_run_at <= $1", now,
            )
            jobs = [_record_to_job(r) for r in rows] if rows else []

            if jobs:
                log.info("cron tick: %d due job(s) — %s", len(jobs),
                         ", ".join(j.name for j in jobs))

                results = await asyncio.gather(
                    *[self._execute_job(job) for job in jobs],
                    return_exceptions=True,
                )

                for job, result in zip(jobs, results):
                    await self._apply_result(job, result)

        except Exception as e:
            log.error("cron tick error: %s", e)
        finally:
            self._ticking = False
            await self._arm_timer()

    async def _execute_job(self, job: CronJob) -> str:
        """Execute a single job within semaphore. Returns reply text."""
        async with self._sem:
            log.info("executing job: %s (%s) mode=%s", job.name, job.id, job.session_mode)

            # Build per-job system prompt
            system_prompt = get_system_prompt()
            task_header = f"\n\n---\n\n[Scheduled Task: {job.name}]"
            if job.context:
                system_prompt += task_header + "\n" + job.context
            else:
                system_prompt += task_header

            # Use session key for persistent mode, or isolated
            if job.session_mode == "persistent":
                session_key = cron_key(job.id)
            else:
                session_key = cron_key(job.id, isolated=True)

            # Use the unified LLM entry point
            from bot import llm
            reply = await llm.reply(session_key, job.payload)

            # Deliver result through Gateway
            if reply.strip():
                from bot.gateway import get_gateway
                gw = get_gateway()
                if gw:
                    reply_ctx = {"target_id": job.channel_id}
                    result = await gw.deliver(job.delivery_channel, reply_ctx, reply)
                    log.info("job %s delivered via %s to %s: %s",
                             job.name, job.delivery_channel, job.channel_id, result)
                elif self._bot and job.delivery_channel == "discord":
                    # Fallback: Discord delivery without gateway
                    try:
                        channel = self._bot.get_channel(int(job.channel_id))
                        if channel is None:
                            channel = await self._bot.fetch_channel(int(job.channel_id))
                        await send_chunks(channel, reply)
                        log.info("job %s delivered to channel %s (%d chars)", job.name, job.channel_id, len(reply))
                    except Exception as e:
                        log.error("job %s delivery failed: %s", job.name, e)
                        raise
                else:
                    log.error("job %s: no gateway and no bot for delivery via %s", job.name, job.delivery_channel)

            return reply

    async def _apply_result(self, job: CronJob, result: str | BaseException) -> None:
        """Update job state after execution."""
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
        """Update job state in PostgreSQL."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            if enabled is not None and not enabled:
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


# Module-level singleton
_scheduler: CronScheduler | None = None


def get_scheduler() -> CronScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler
