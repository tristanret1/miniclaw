"""health_log, health_stats, health_goal tool schemas."""

HEALTH_LOG_TOOL = {
    "name": "health_log",
    "description": (
        "Log health data: weight, sleep, or exercise. "
        "Use this whenever the user reports their weight, sleep, or workout. "
        "For exercise, intensity levels: 'low' (walking, stretching), "
        "'moderate' (brisk walking, cycling, yoga), 'high'/'vigorous' (running, HIIT, swimming laps). "
        "Weekly goal: 150+ minutes of moderate-to-high intensity exercise."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["weight", "sleep", "exercise"],
                "description": "Type of health data to log.",
            },
            "date": {
                "type": "string",
                "description": "Date for the entry (YYYY-MM-DD). Defaults to today.",
            },
            # weight fields
            "value": {
                "type": "number",
                "description": "(weight) Weight value, e.g. 75.5.",
            },
            "unit": {
                "type": "string",
                "description": "(weight) Unit: 'kg' or 'lb'. Default: kg.",
            },
            # sleep fields
            "hours": {
                "type": "number",
                "description": "(sleep) Hours slept, e.g. 7.5.",
            },
            "quality": {
                "type": "string",
                "enum": ["great", "good", "fair", "poor"],
                "description": "(sleep) Sleep quality rating.",
            },
            "bedtime": {
                "type": "string",
                "description": "(sleep) Bedtime, e.g. '23:00'.",
            },
            "wake_time": {
                "type": "string",
                "description": "(sleep) Wake time, e.g. '06:30'.",
            },
            # exercise fields
            "activity": {
                "type": "string",
                "description": "(exercise) Activity name, e.g. 'running', 'cycling', 'HIIT', 'yoga'.",
            },
            "duration_minutes": {
                "type": "integer",
                "description": "(exercise) Duration in minutes.",
            },
            "intensity": {
                "type": "string",
                "enum": ["low", "moderate", "high", "vigorous"],
                "description": "(exercise) Intensity level. 'moderate' and above count toward 150min/week goal.",
            },
            "calories": {
                "type": "integer",
                "description": "(exercise) Estimated calories burned (optional).",
            },
            "notes": {
                "type": "string",
                "description": "(exercise) Additional notes.",
            },
        },
        "required": ["type"],
    },
}

HEALTH_STATS_TOOL = {
    "name": "health_stats",
    "description": (
        "Query health statistics and progress. Shows exercise progress toward "
        "150min/week goal, weight trend with goal tracking, sleep averages, "
        "or a combined overview."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "stat_type": {
                "type": "string",
                "enum": ["exercise", "weight", "sleep", "overview"],
                "description": "Type of stats: 'exercise' (weekly 150min goal), 'weight' (trend + goal), 'sleep' (averages), 'overview' (all combined).",
            },
            "days": {
                "type": "integer",
                "description": "Lookback period in days (default 30 for weight, 7 for sleep).",
            },
        },
        "required": ["stat_type"],
    },
}

HEALTH_GOAL_TOOL = {
    "name": "health_goal",
    "description": (
        "Set a weight loss / gain goal. Tracks current weight against target "
        "with a deadline. Progress shown in health_stats weight trend."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "start_weight": {
                "type": "number",
                "description": "Current / starting weight in kg.",
            },
            "target_weight": {
                "type": "number",
                "description": "Target weight in kg.",
            },
            "target_date": {
                "type": "string",
                "description": "Target date (YYYY-MM-DD).",
            },
        },
        "required": ["start_weight", "target_weight", "target_date"],
    },
}
