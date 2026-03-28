"""memory_save and memory_search tool schemas."""

MEMORY_SAVE_TOOL = {
    "name": "memory_save",
    "description": (
        "Save a piece of information to long-term memory. Use this to remember "
        "user preferences, important facts, decisions, or anything worth recalling later. "
        "Memories are stored as daily Markdown logs."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The information to remember.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags for categorization (e.g. ['preference', 'user']).",
            },
        },
        "required": ["content"],
    },
}

MEMORY_SEARCH_TOOL = {
    "name": "memory_search",
    "description": (
        "Search long-term memory for previously saved information. "
        "Use this when the user references past conversations, preferences, "
        "or facts that may have been stored."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords to search for in memory.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default 10).",
            },
        },
        "required": ["query"],
    },
}
