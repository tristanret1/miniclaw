"""Tool definitions and execution for Claude tool use."""

import asyncio
import os

# Max output length to avoid flooding Discord / Claude context
MAX_OUTPUT_CHARS = 4000
DEFAULT_TIMEOUT = 30


EXEC_TOOL = {
    "name": "exec",
    "description": (
        "Execute a shell command on the host machine and return its output. "
        "Use this for system tasks like listing files, checking disk usage, "
        "running scripts, installing packages, etc."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30, max 120).",
            },
            "workdir": {
                "type": "string",
                "description": "Working directory for the command.",
            },
        },
        "required": ["command"],
    },
}

ALL_TOOLS = [EXEC_TOOL]


async def run_exec(command: str, timeout: int = DEFAULT_TIMEOUT, workdir: str | None = None) -> str:
    timeout = min(max(timeout, 1), 120)
    cwd = workdir if workdir and os.path.isdir(workdir) else None

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return f"[Timed out after {timeout}s]"

    output = ""
    if stdout:
        output += stdout.decode(errors="replace")
    if stderr:
        output += ("\n--- stderr ---\n" + stderr.decode(errors="replace"))

    if not output.strip():
        output = f"[No output, exit code {proc.returncode}]"
    elif proc.returncode != 0:
        output += f"\n[exit code {proc.returncode}]"

    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(output)} chars total]"

    return output


async def handle_tool_call(tool_name: str, tool_input: dict) -> str:
    if tool_name == "exec":
        return await run_exec(
            command=tool_input["command"],
            timeout=tool_input.get("timeout", DEFAULT_TIMEOUT),
            workdir=tool_input.get("workdir"),
        )
    return f"Unknown tool: {tool_name}"
