"""Google Calendar API wrapper — list, create, update, delete events."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bot.config import get_config, get_secrets
from bot.logger import get_logger

log = get_logger("google_calendar")


def _build_service(account: str = ""):
    """Build an authorized Google Calendar API service client.

    Args:
        account: "life", "work", or "" (legacy fallback).
    """
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    from bot.google_oauth import get_valid_credentials

    creds_dict = get_valid_credentials(account=account)
    if creds_dict is None:
        label = f" ({account})" if account else ""
        raise RuntimeError(
            f"Google Calendar authentication expired{label}. Please re-run setup."
        )

    creds = Credentials(
        token=creds_dict["access_token"],
        refresh_token=creds_dict.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=creds_dict.get("client_id"),
        client_secret=creds_dict.get("client_secret"),
    )
    return build("calendar", "v3", credentials=creds)


def _parse_event(event: dict, source_calendar: str) -> dict:
    """Convert Google Calendar API event dict to standardized format."""
    start = event.get("start", {})
    end = event.get("end", {})

    # All-day events use "date", timed events use "dateTime"
    is_all_day = "date" in start and "dateTime" not in start
    start_str = start.get("dateTime", start.get("date", ""))
    end_str = end.get("dateTime", end.get("date", ""))

    return {
        "id": event.get("id", ""),
        "title": event.get("summary", "(No title)"),
        "start": start_str,
        "end": end_str,
        "description": event.get("description", ""),
        "location": event.get("location", ""),
        "source_calendar": source_calendar,
        "is_all_day": is_all_day,
    }


def _get_calendar_id(calendar: str) -> str:
    """Resolve calendar name to Google Calendar ID."""
    gcal = get_config().services.google_calendar
    if calendar == "life":
        return gcal.life_calendar_id
    if calendar == "work":
        return gcal.work_calendar_id
    raise ValueError(f"Unknown calendar: {calendar}")


def _fetch_events(
    service, calendar_id: str, source_name: str, time_min: str, time_max: str
) -> list[dict]:
    """Fetch events from a single calendar."""
    try:
        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                timeZone=get_config().services.cron.timezone,
            )
            .execute()
        )
        return [_parse_event(e, source_name) for e in result.get("items", [])]
    except Exception as e:
        log.error("Failed to fetch events from %s: %s", source_name, e)
        raise


def list_events(
    calendar: str = "both",
    date_start: str = "",
    date_end: str = "",
) -> list[dict]:
    """List events from Life, Work, or both calendars, merged and sorted."""
    # Default to today if no range specified
    _gcal_cfg = get_config().services.google_calendar
    _cron_tz = get_config().services.cron.timezone
    tz = ZoneInfo(_cron_tz)
    now = datetime.now(tz)
    if not date_start:
        date_start = now.replace(hour=0, minute=0, second=0).isoformat()
    if not date_end:
        date_end = (now.replace(hour=0, minute=0, second=0) + timedelta(days=1)).isoformat()

    # Ensure timezone info in ISO strings
    if not date_start.endswith("Z") and "+" not in date_start and "-" not in date_start[10:]:
        date_start = date_start + tz.utcoffset(now).isoformat() if hasattr(tz.utcoffset(now), "isoformat") else date_start

    events: list[dict] = []

    if calendar in ("life", "both"):
        if _gcal_cfg.life_calendar_id:
            service = _build_service(account="life")
            events.extend(
                _fetch_events(service, _gcal_cfg.life_calendar_id, "Life", date_start, date_end)
            )

    if calendar in ("work", "both"):
        if _gcal_cfg.work_calendar_id:
            service = _build_service(account="work")
            events.extend(
                _fetch_events(service, _gcal_cfg.work_calendar_id, "Work", date_start, date_end)
            )

    # Sort by start time
    events.sort(key=lambda e: e["start"])
    return events


def format_events(events: list[dict]) -> str:
    """Format event list into a human-readable string."""
    if not events:
        return "No events found for this period."

    lines: list[str] = []
    tz = ZoneInfo(get_config().services.cron.timezone)

    for ev in events:
        cal_label = f"[{ev['source_calendar']}]"

        if ev["is_all_day"]:
            time_str = "All day"
        else:
            try:
                start_dt = datetime.fromisoformat(ev["start"])
                end_dt = datetime.fromisoformat(ev["end"])
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=tz)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=tz)
                time_str = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
            except (ValueError, TypeError):
                time_str = f"{ev['start']} - {ev['end']}"

        line = f"{time_str} {cal_label} {ev['title']}"
        lines.append(line)

    count = len(events)
    header = f"📅 {count} event{'s' if count != 1 else ''} found:\n"
    return header + "\n".join(lines)


def create_event(
    title: str,
    start_time: str,
    end_time: str = "",
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
) -> dict:
    """Create an event on the Life calendar. Returns created event dict."""
    _gcal_cfg = get_config().services.google_calendar
    _cron_tz = get_config().services.cron.timezone
    if not _gcal_cfg.life_calendar_id:
        raise RuntimeError("Life calendar not configured (life_calendar_id)")

    service = _build_service(account="life")
    tz = ZoneInfo(_cron_tz)

    # Parse start time
    start_dt = datetime.fromisoformat(start_time)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=tz)

    # Default end time: start + 1 hour
    if end_time:
        end_dt = datetime.fromisoformat(end_time)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=tz)
    else:
        end_dt = start_dt + timedelta(hours=1)

    event_body = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": _cron_tz},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": _cron_tz},
    }
    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location
    if attendees:
        event_body["attendees"] = [{"email": e} for e in attendees]

    result = (
        service.events()
        .insert(calendarId=_gcal_cfg.life_calendar_id, body=event_body)
        .execute()
    )

    created = _parse_event(result, "Life")
    log.info("Created event '%s' on Life calendar (id=%s)", title, created["id"])
    return created


def update_event(event_id: str, updates: dict) -> dict:
    """Update a Life calendar event. Returns updated event dict."""
    _gcal_cfg = get_config().services.google_calendar
    _cron_tz = get_config().services.cron.timezone
    if not _gcal_cfg.life_calendar_id:
        raise RuntimeError("Life calendar not configured (life_calendar_id)")

    service = _build_service(account="life")
    tz = ZoneInfo(_cron_tz)

    patch_body: dict = {}
    if "title" in updates:
        patch_body["summary"] = updates["title"]
    if "description" in updates:
        patch_body["description"] = updates["description"]
    if "location" in updates:
        patch_body["location"] = updates["location"]
    if "start_time" in updates:
        start_dt = datetime.fromisoformat(updates["start_time"])
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=tz)
        patch_body["start"] = {"dateTime": start_dt.isoformat(), "timeZone": _cron_tz}
    if "end_time" in updates:
        end_dt = datetime.fromisoformat(updates["end_time"])
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=tz)
        patch_body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": _cron_tz}
    if "attendees" in updates:
        patch_body["attendees"] = [{"email": e} for e in updates["attendees"]]

    result = (
        service.events()
        .patch(calendarId=_gcal_cfg.life_calendar_id, eventId=event_id, body=patch_body)
        .execute()
    )

    updated = _parse_event(result, "Life")
    log.info("Updated event %s on Life calendar", event_id)
    return updated


async def delete_event(event_id: str) -> str:
    """Delete a Life calendar event. Returns confirmation string."""
    life_id = get_config().services.google_calendar.life_calendar_id
    if not life_id:
        raise RuntimeError("Life calendar not configured (life_calendar_id)")

    service = _build_service(account="life")
    service.events().delete(
        calendarId=life_id, eventId=event_id
    ).execute()

    # Clean up any associated reminder cron job
    job_id = _find_reminder_job(event_id)
    if job_id:
        from bot import cron
        await cron.delete_job(job_id)
        log.info("Deleted reminder job %s for event %s", job_id, event_id)

    log.info("Deleted event %s from Life calendar", event_id)
    return f"Event {event_id} deleted from Life calendar."


async def _schedule_urgent_reminder(
    event_id: str,
    event_title: str,
    event_start: str,
    reminder_minutes: int = 15,
    reminder_channel: str = "phone_call",
    channel_id: str = "",
) -> str:
    """Schedule a one-shot cron job as an urgent event reminder."""
    from bot import cron

    _cron_tz = get_config().services.cron.timezone
    tz = ZoneInfo(_cron_tz)
    start_dt = datetime.fromisoformat(event_start)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=tz)

    fire_at = start_dt - timedelta(minutes=reminder_minutes)

    # Build cascade instruction payload
    payload = (
        f"URGENT REMINDER: '{event_title}' starts in {reminder_minutes} minutes. "
        f"You MUST deliver this reminder immediately. "
        f"First, try using the {reminder_channel} tool to call/text the user. "
        f"If {reminder_channel} fails, try sms tool. "
        f"If sms also fails, send a Discord message. "
        f"Include the event title and start time in the reminder message."
    )

    context = f"calendar_event_id:{event_id}"

    job_result = await cron.create_job(
        name=f"Reminder: {event_title}",
        schedule_type="at",
        schedule_value=fire_at.isoformat(),
        payload=payload,
        channel_id=channel_id,
        timezone=_cron_tz,
        session_mode="isolated",
        context=context,
    )

    log.info(
        "Scheduled urgent reminder for '%s' at %s via %s",
        event_title,
        fire_at.isoformat(),
        reminder_channel,
    )
    return job_result


def _find_reminder_job(event_id: str) -> str | None:
    """Find a cron job associated with a calendar event. Returns job_id or None."""
    try:
        from bot.cron import _get_db

        context_marker = f"calendar_event_id:{event_id}"
        db = _get_db()
        row = db.execute(
            "SELECT id FROM cron_jobs WHERE context LIKE ?",
            (f"%{context_marker}%",),
        ).fetchone()
        if row:
            return row[0]
    except Exception as e:
        log.warning("Failed to search for reminder job for event %s: %s", event_id, e)

    return None
