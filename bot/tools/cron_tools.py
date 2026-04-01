"""cron_create, cron_list, cron_delete tool schemas."""

CRON_CREATE_TOOL = {
    "name": "cron_create",
    "description": (
        "Create a scheduled/recurring task. The task message will be sent to "
        "Claude at the scheduled time, and the response delivered to a Discord channel. "
        "Use 'context' to define per-job personality/instructions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Human-readable name for this job.",
            },
            "schedule_type": {
                "type": "string",
                "enum": ["every", "cron", "at"],
                "description": "Schedule type: 'every' for interval, 'cron' for cron expression, 'at' for one-shot.",
            },
            "schedule_value": {
                "type": "string",
                "description": "Schedule value. every: '30m','2h','1d'. cron: '0 8 * * *'. at: ISO time or '+20m'.",
            },
            "payload": {
                "type": "string",
                "description": "The message/task to send to Claude when the job fires.",
            },
            "channel_id": {
                "type": "string",
                "description": "Discord channel ID to deliver results to.",
            },
            "timezone": {
                "type": "string",
                "description": "IANA timezone (default: America/Vancouver).",
            },
            "session_mode": {
                "type": "string",
                "enum": ["isolated", "persistent"],
                "description": "Session mode. 'isolated' (default): fresh each run. 'persistent': carry conversation history across runs.",
            },
            "context": {
                "type": "string",
                "description": "Extra system instructions for this job. Defines the job's personality, output format, focus areas, language, etc.",
            },
            "model": {
                "type": "string",
                "description": "Model override (e.g. 'claude-haiku-4-5-20251001' for simple tasks). Empty = use global default.",
            },
            "delivery_channel": {
                "type": "string",
                "enum": ["discord", "sms", "imessage", "feishu"],
                "description": "Delivery channel: 'discord' (default) sends to Discord channel_id, 'sms' sends SMS via Twilio, 'imessage' sends via iMessage, 'feishu' sends to Feishu chat. For sms/imessage, channel_id should be E.164 phone number or Apple ID. For feishu, use chat_id (oc_xxx).",
            },
        },
        "required": ["name", "schedule_type", "schedule_value", "payload", "channel_id"],
    },
}

CRON_LIST_TOOL = {
    "name": "cron_list",
    "description": "List all scheduled tasks with their status and next run time.",
    "input_schema": {
        "type": "object",
        "properties": {
            "include_disabled": {
                "type": "boolean",
                "description": "Include disabled/completed jobs (default: false).",
            },
        },
    },
}

CRON_DELETE_TOOL = {
    "name": "cron_delete",
    "description": "Delete a scheduled task by ID or name.",
    "input_schema": {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "Job ID or name to delete.",
            },
        },
        "required": ["job_id"],
    },
}
