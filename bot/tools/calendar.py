"""google_calendar tool schema and handler."""

from bot.logger import get_logger

log = get_logger("tools")

GOOGLE_CALENDAR_TOOL = {
    "name": "google_calendar",
    "description": (
        "Manage Google Calendar events. Supports listing, creating, updating, and "
        "deleting events. Life calendar is read-write, Work calendar is read-only. "
        "Events can be marked as urgent to trigger phone/SMS reminders."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "create", "update", "delete"],
                "description": "The operation to perform.",
            },
            "calendar": {
                "type": "string",
                "enum": ["life", "work", "both"],
                "description": "Which calendar to operate on. 'both' merges Life and Work (list only). Default: 'both' for list, 'life' for create/update/delete.",
            },
            "date_start": {
                "type": "string",
                "description": "Start of date range (ISO 8601). Required for list.",
            },
            "date_end": {
                "type": "string",
                "description": "End of date range (ISO 8601). Required for list.",
            },
            "event_id": {
                "type": "string",
                "description": "Google Calendar event ID. Required for update and delete.",
            },
            "title": {
                "type": "string",
                "description": "Event title/summary. Required for create.",
            },
            "start_time": {
                "type": "string",
                "description": "Event start time (ISO 8601). Required for create.",
            },
            "end_time": {
                "type": "string",
                "description": "Event end time (ISO 8601). Defaults to start_time + 1 hour.",
            },
            "description": {
                "type": "string",
                "description": "Optional event description.",
            },
            "location": {
                "type": "string",
                "description": "Optional event location.",
            },
            "urgent": {
                "type": "boolean",
                "description": "Mark event as urgent (triggers reminder). Only for create. Default: false.",
            },
            "reminder_minutes": {
                "type": "integer",
                "description": "Minutes before event to trigger reminder. Only when urgent=true. Default: 15.",
            },
            "reminder_channel": {
                "type": "string",
                "enum": ["phone_call", "sms"],
                "description": "Primary reminder delivery channel. Default: 'phone_call'. Cascade fallback: phone_call → sms → discord.",
            },
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of attendee email addresses. Optional, for create and update actions.",
            },
            "updates": {
                "type": "object",
                "description": "Fields to update (for action=update). Keys: title, start_time, end_time, description, location, attendees.",
                "properties": {
                    "title": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attendee email addresses.",
                    },
                },
            },
        },
        "required": ["action"],
    },
}


async def run_google_calendar(action: str, **kwargs) -> str:
    """Handle google_calendar tool actions."""
    from bot.services import google_calendar as gcal

    try:
        if action == "list":
            date_start = kwargs.get("date_start", "")
            date_end = kwargs.get("date_end", "")
            calendar = kwargs.get("calendar", "both")
            if not date_start or not date_end:
                return "Error: Missing required parameter: date_start and date_end are required for list action."
            events = gcal.list_events(calendar=calendar, date_start=date_start, date_end=date_end)
            return gcal.format_events(events)

        if action == "create":
            title = kwargs.get("title", "")
            start_time = kwargs.get("start_time", "")
            if not title:
                return "Error: Missing required parameter: title"
            if not start_time:
                return "Error: Missing required parameter: start_time"

            calendar = kwargs.get("calendar", "life")
            if calendar == "work":
                return "Error: Work calendar is read-only. Use Google Calendar directly for work events."

            created = gcal.create_event(
                title=title,
                start_time=start_time,
                end_time=kwargs.get("end_time", ""),
                description=kwargs.get("description", ""),
                location=kwargs.get("location", ""),
                attendees=kwargs.get("attendees"),
            )

            result = (
                f"✅ Created event on Life calendar:\n"
                f"  Title: {created['title']}\n"
                f"  Time: {created['start']} - {created['end']}"
            )

            # Schedule urgent reminder if requested
            if kwargs.get("urgent", False):
                reminder_minutes = kwargs.get("reminder_minutes", 15)
                reminder_channel = kwargs.get("reminder_channel", "phone_call")
                channel_id = kwargs.get("_channel_id", "")
                await gcal._schedule_urgent_reminder(
                    event_id=created["id"],
                    event_title=created["title"],
                    event_start=created["start"],
                    reminder_minutes=reminder_minutes,
                    reminder_channel=reminder_channel,
                    channel_id=channel_id,
                )
                result += f"\n  🚨 Urgent: {reminder_channel} reminder {reminder_minutes} min before"

            return result

        if action == "update":
            event_id = kwargs.get("event_id", "")
            updates = kwargs.get("updates", {})
            if not event_id:
                return "Error: Missing required parameter: event_id"
            if not updates:
                return "Error: Missing required parameter: updates"

            calendar = kwargs.get("calendar", "life")
            if calendar == "work":
                return "Error: Work calendar is read-only. Use Google Calendar directly for work events."

            # If start_time changes, handle reminder update
            if "start_time" in updates:
                job_id = await gcal._find_reminder_job(event_id)
                if job_id:
                    from bot import cron
                    await cron.delete_job(job_id)
                    # Note: Claude should re-create the reminder if still needed

            updated = gcal.update_event(event_id=event_id, updates=updates)
            fields = ", ".join(updates.keys())
            return f"✅ Updated event on Life calendar:\n  ID: {event_id}\n  Updated fields: {fields}"

        if action == "delete":
            event_id = kwargs.get("event_id", "")
            if not event_id:
                return "Error: Missing required parameter: event_id"

            calendar = kwargs.get("calendar", "life")
            if calendar == "work":
                return "Error: Work calendar is read-only. Use Google Calendar directly for work events."

            return await gcal.delete_event(event_id=event_id)

        return f"Error: Unknown action '{action}'. Valid actions: list, create, update, delete."

    except RuntimeError as e:
        return f"Error: {e}"
    except Exception as e:
        log.error("google_calendar error (action=%s): %s", action, e)
        if "429" in str(e) or "rate" in str(e).lower():
            return "Error: Google Calendar API rate limit reached. Please try again in a moment."
        if "401" in str(e) or "auth" in str(e).lower():
            return "Error: Google Calendar authentication expired. Please re-run setup."
        return f"Error: Google Calendar operation failed — {e}"
