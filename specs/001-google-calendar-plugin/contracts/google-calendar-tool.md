# Tool Contract: google_calendar

**Type**: LLM Tool (Anthropic tool_use schema)

## Tool Definition

```json
{
  "name": "google_calendar",
  "description": "Manage Google Calendar events. Supports listing, creating, updating, and deleting events. Life calendar is read-write, Work calendar is read-only. Events can be marked as urgent to trigger phone/SMS reminders.",
  "input_schema": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["list", "create", "update", "delete"],
        "description": "The operation to perform."
      },
      "calendar": {
        "type": "string",
        "enum": ["life", "work", "both"],
        "description": "Which calendar to operate on. 'both' merges Life and Work (list only). Default: 'both' for list, 'life' for create/update/delete."
      },
      "date_start": {
        "type": "string",
        "description": "Start of date range (ISO 8601, e.g., '2026-03-23T00:00:00'). Required for list."
      },
      "date_end": {
        "type": "string",
        "description": "End of date range (ISO 8601). Required for list."
      },
      "event_id": {
        "type": "string",
        "description": "Google Calendar event ID. Required for update and delete."
      },
      "title": {
        "type": "string",
        "description": "Event title/summary. Required for create."
      },
      "start_time": {
        "type": "string",
        "description": "Event start time (ISO 8601). Required for create."
      },
      "end_time": {
        "type": "string",
        "description": "Event end time (ISO 8601). Defaults to start_time + 1 hour."
      },
      "description": {
        "type": "string",
        "description": "Optional event description."
      },
      "location": {
        "type": "string",
        "description": "Optional event location."
      },
      "urgent": {
        "type": "boolean",
        "description": "Mark event as urgent (triggers reminder). Only for create. Default: false."
      },
      "reminder_minutes": {
        "type": "integer",
        "description": "Minutes before event to trigger reminder. Only when urgent=true. Default: 15."
      },
      "reminder_channel": {
        "type": "string",
        "enum": ["phone_call", "sms"],
        "description": "Primary reminder delivery channel. Default: 'phone_call'. Cascade fallback: phone_call → sms → discord."
      },
      "updates": {
        "type": "object",
        "description": "Fields to update (for action=update). Keys: title, start_time, end_time, description, location.",
        "properties": {
          "title": { "type": "string" },
          "start_time": { "type": "string" },
          "end_time": { "type": "string" },
          "description": { "type": "string" },
          "location": { "type": "string" }
        }
      }
    },
    "required": ["action"]
  }
}
```

## Action Contracts

### list

**Required params**: `action`, `date_start`, `date_end`
**Optional params**: `calendar` (default: "both")

**Returns**: Formatted string with merged event list, sorted by start time. Each event labeled `[Life]` or `[Work]`. Urgent events marked with indicator.

**Example output**:
```
📅 Schedule for Mar 23, 2026:

09:00 - 10:00 [Work] Team standup
12:00 - 13:00 [Life] Lunch with Alice
🚨 14:00 - 15:00 [Life] Dentist appointment (reminder: phone call at 13:45)
17:00 - 18:00 [Work] 1:1 with manager

4 events found.
```

### create

**Required params**: `action`, `title`, `start_time`
**Optional params**: `end_time`, `description`, `location`, `urgent`, `reminder_minutes`, `reminder_channel`
**Constraints**: Always creates on Life calendar. Rejects `calendar="work"`.

**Returns**: Confirmation with event details and reminder info (if urgent).

**Example output**:
```
✅ Created event on Life calendar:
  Title: Dentist appointment
  Time: Mar 24, 2026 14:00 - 15:00
  🚨 Urgent: Phone call reminder at 13:45
```

### update

**Required params**: `action`, `event_id`, `updates`
**Constraints**: Only Life calendar events. Rejects Work calendar event IDs.

**Returns**: Confirmation with updated fields.

### delete

**Required params**: `action`, `event_id`
**Constraints**: Only Life calendar events. Rejects Work calendar event IDs.

**Returns**: Confirmation of deletion. Also cancels associated reminder cron job if one exists.

## Error Responses

| Scenario | Response |
| -------- | -------- |
| Work calendar write attempt | "Error: Work calendar is read-only. Use Google Calendar directly for work events." |
| Invalid event_id | "Error: Event not found. It may have been deleted or the ID is incorrect." |
| Auth token expired + refresh failed | "Error: Google Calendar authentication expired. Please re-run setup." |
| API rate limit | "Error: Google Calendar API rate limit reached. Please try again in a moment." |
| Missing required params | "Error: Missing required parameter: {param_name}" |
