"""claude_code tool — delegate tasks to Claude Code agent via ACP."""

CLAUDE_CODE_TOOL = {
    "name": "claude_code",
    "description": (
        "Delegate a coding task to Claude Code (an autonomous coding agent) via ACP. "
        "Use this for complex programming tasks: writing code, debugging, refactoring, "
        "reading/editing files in a project, running tests, git operations, etc. "
        "Claude Code has full access to the filesystem and terminal."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The coding task to delegate. Be specific about what to do, which files, and expected outcome.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the task (defaults to ACP_CWD or current dir).",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 300, max 600).",
            },
        },
        "required": ["task"],
    },
}
