"""Heartbeat — periodic agent polling system.

Default-silent: if nothing needs attention, agent replies HEARTBEAT_OK
and the message is discarded without disturbing the user.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.constants import HEARTBEAT_TOKEN
from bot.logger import get_logger
from bot.utils.session_keys import heartbeat_key

log = get_logger("heartbeat")

HEARTBEAT_PROMPT = (
    "Read HEARTBEAT.md if it exists (workspace context). Follow it strictly. "
    "Do not infer or repeat old tasks from prior chats. "
    "If nothing needs attention, reply HEARTBEAT_OK."
)

DEFAULT_INTERVAL = "30m"
DEFAULT_ACK_MAX_CHARS = 300

# ── Duration parsing ─────────────────────────────────────────────────────────

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


# ── HEARTBEAT.md content check ───────────────────────────────────────────────

_EMPTY_LINE_RE = re.compile(r"^\s*$")
_HEADER_RE = re.compile(r"^#+(\s|$)")
_EMPTY_LIST_RE = re.compile(r"^[-*+]\s*(\[[\sXx]?\]\s*)?$")


def is_heartbeat_content_empty(content: str) -> bool:
    """Check if HEARTBEAT.md content is effectively empty (only headers/blanks).

    Returns True if no actionable checklist items found.
    """
    for line in content.splitlines():
        line = line.strip()
        if _EMPTY_LINE_RE.match(line):
            continue
        if _HEADER_RE.match(line):
            continue
        if _EMPTY_LIST_RE.match(line):
            continue
        # Found an actionable line
        return False
    return True


def read_heartbeat_file(workspace_dir: Path) -> str | None:
    """Read HEARTBEAT.md from workspace. Returns None if missing or empty."""
    path = workspace_dir / "HEARTBEAT.md"
    if not path.exists():
        return None
    content = path.read_text().strip()
    if not content or is_heartbeat_content_empty(content):
        return None
    return content


# ── Token stripping ──────────────────────────────────────────────────────────

# Matches HEARTBEAT_OK at start/end with optional trailing punctuation
_TOKEN_START_RE = re.compile(r"^HEARTBEAT_OK[^\w]{0,4}\s*", re.IGNORECASE)
_TOKEN_END_RE = re.compile(r"\s*HEARTBEAT_OK[^\w]{0,4}\s*$", re.IGNORECASE)

# Strip HTML tags and markdown code wrappers
_MARKUP_RE = re.compile(r"<[^>]+>")


def strip_heartbeat_token(
    raw: str,
    ack_max_chars: int = DEFAULT_ACK_MAX_CHARS,
) -> tuple[bool, str, bool]:
    """Strip HEARTBEAT_OK token from response text.

    Returns:
        (should_skip, cleaned_text, did_strip)
        - should_skip: True if remaining text ≤ ack_max_chars (discard message)
        - cleaned_text: text with token removed
        - did_strip: whether token was found
    """
    text = raw.strip()

    # Normalize markup
    text = _MARKUP_RE.sub("", text)
    text = text.replace("&nbsp;", " ")

    # Strip token at edges (loop until stable)
    did_strip = False
    prev = None
    while prev != text:
        prev = text
        m = _TOKEN_START_RE.search(text)
        if m:
            text = text[m.end():]
            did_strip = True
        m = _TOKEN_END_RE.search(text)
        if m:
            text = text[:m.start()]
            did_strip = True
        text = text.strip()

    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text).strip()

    should_skip = did_strip and len(text) <= ack_max_chars
    return should_skip, text, did_strip


# ── Active hours ─────────────────────────────────────────────────────────────

def is_within_active_hours(
    start: str | None,
    end: str | None,
    timezone: str = "",
) -> bool:
    """Check if current time is within active hours window.

    Args:
        start: "HH:MM" (24h), inclusive. None = no restriction.
        end: "HH:MM" (24h) or "24:00", exclusive. None = no restriction.
        timezone: IANA timezone string, empty = local.

    Returns True if within active hours or no config set.
    """
    if not start or not end:
        return True

    time_re = re.compile(r"^(?:([01]\d|2[0-3]):([0-5]\d)|24:00)$")

    m_start = time_re.match(start)
    m_end = time_re.match(end)
    if not m_start or not m_end:
        log.warning("invalid active hours: start=%r end=%r — allowing heartbeat", start, end)
        return True  # Fail-open

    start_min = int(m_start.group(1) or 24) * 60 + int(m_start.group(2) or 0)
    end_min = int(m_end.group(1) or 24) * 60 + int(m_end.group(2) or 0)

    if start_min == end_min:
        return False  # Disabled

    # Get current time in configured timezone
    try:
        tz = ZoneInfo(timezone) if timezone else None
        now = datetime.now(tz)
    except Exception:
        now = datetime.now()

    current_min = now.hour * 60 + now.minute

    if end_min > start_min:
        return start_min <= current_min < end_min
    else:
        # Wraps midnight
        return current_min >= start_min or current_min < end_min


# ── Real-world context ───────────────────────────────────────────────────────

def _get_today_calendar() -> str | None:
    """Fetch today's calendar events. Returns None if calendar not enabled."""
    from bot.config import get_config
    if not get_config().services.google_calendar.enabled:
        return None
    try:
        from bot.services import google_calendar as gcal
        today = datetime.now().strftime("%Y-%m-%d")
        start = f"{today}T00:00:00"
        end = f"{today}T23:59:59"
        events = gcal.list_events(calendar="both", date_start=start, date_end=end)
        return gcal.format_events(events)
    except Exception as e:
        log.warning("failed to fetch calendar for heartbeat: %s", e)
        return None


# ── Heartbeat runner ─────────────────────────────────────────────────────────

class HeartbeatRunner:
    """Periodic heartbeat runner for a single agent."""

    def __init__(
        self,
        agent,
        deliver_fn,
        *,
        channel_id: str = "",
        interval: str = "",
        active_hours_start: str = "",
        active_hours_end: str = "",
        active_hours_tz: str = "",
        ack_max_chars: int = DEFAULT_ACK_MAX_CHARS,
        isolated_session: bool = True,
    ):
        self.agent = agent
        self._deliver_fn = deliver_fn  # async fn(text: str) -> None
        self._channel_id = channel_id
        self._interval = interval or DEFAULT_INTERVAL
        self._active_start = active_hours_start
        self._active_end = active_hours_end
        self._active_tz = active_hours_tz
        self._ack_max_chars = ack_max_chars
        self._isolated = isolated_session

        self._running = False
        self._task: asyncio.Task | None = None
        self._interval_sec = _parse_duration_seconds(self._interval)

        # Dedup state
        self._last_text: str | None = None
        self._last_sent_at: float | None = None

    async def start(self) -> None:
        """Start the heartbeat loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info(
            "heartbeat started for agent '%s' (interval=%s, isolated=%s)",
            self.agent.name, self._interval, self._isolated,
        )

    def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        log.info("heartbeat stopped for agent '%s'", self.agent.name)

    async def run_once(self, reason: str = "interval") -> str:
        """Execute a single heartbeat run.

        Returns: status string ("sent", "ok-empty", "skipped:<reason>")
        """
        import time

        # Gate: active hours
        if not is_within_active_hours(self._active_start, self._active_end, self._active_tz):
            log.debug("heartbeat skipped: outside active hours")
            return "skipped:active-hours"

        # Gate: HEARTBEAT.md content
        checklist = read_heartbeat_file(self.agent.workspace_dir)
        if checklist is None:
            log.debug("heartbeat skipped: empty HEARTBEAT.md")
            return "skipped:empty-heartbeat-file"

        # Build prompt with real-world context
        context_parts = [HEARTBEAT_PROMPT]

        # Inject today's calendar if available
        calendar_text = _get_today_calendar()
        if calendar_text:
            context_parts.append(f"\n\nToday's calendar:\n{calendar_text}")

        context_parts.append(f"\n\n---\n\nHEARTBEAT.md contents:\n{checklist}")
        prompt = "".join(context_parts)

        # Session key: use channel_id to share memory with the channel
        session_key = heartbeat_key(self._channel_id, isolated=self._isolated)

        # Call LLM
        try:
            from bot import llm
            reply = await llm.reply(session_key, prompt, agent=self.agent)
        except Exception as e:
            log.error("heartbeat LLM call failed: %s", e)
            return f"skipped:error:{e}"

        # Strip token
        should_skip, cleaned, _did_strip = strip_heartbeat_token(reply, self._ack_max_chars)

        if should_skip:
            log.info("heartbeat OK — nothing to report (agent=%s)", self.agent.name)
            return "ok-empty"

        if not cleaned.strip():
            log.info("heartbeat produced empty response (agent=%s)", self.agent.name)
            return "ok-empty"

        # Dedup check (same text within 24h)
        now = time.time()
        if (
            self._last_text == cleaned
            and self._last_sent_at
            and (now - self._last_sent_at) < 86400
        ):
            log.info("heartbeat skipped: duplicate within 24h (agent=%s)", self.agent.name)
            return "skipped:duplicate"

        # Deliver
        try:
            await self._deliver_fn(cleaned)
            self._last_text = cleaned
            self._last_sent_at = now
            log.info(
                "heartbeat delivered (%d chars, agent=%s, reason=%s)",
                len(cleaned), self.agent.name, reason,
            )
            return "sent"
        except Exception as e:
            log.error("heartbeat delivery failed: %s", e)
            return f"skipped:delivery-error:{e}"

    async def _loop(self) -> None:
        """Main heartbeat loop — runs until stopped."""
        # Initial delay: wait one full interval before first heartbeat
        await asyncio.sleep(self._interval_sec)

        while self._running:
            try:
                await self.run_once(reason="interval")
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("heartbeat loop error: %s", e)

            try:
                await asyncio.sleep(self._interval_sec)
            except asyncio.CancelledError:
                break

    async def wake(self, reason: str = "manual") -> str:
        """Trigger an immediate heartbeat run (outside the normal schedule)."""
        return await self.run_once(reason=reason)
