"""exec tool — run shell commands on the host machine."""

import asyncio
import os
import time

from bot.config import get_secrets
from bot.constants import EXEC_DEFAULT_TIMEOUT, TOOL_MAX_OUTPUT_CHARS
from bot.logger import get_logger

log = get_logger("tools")

MAX_OUTPUT_CHARS = TOOL_MAX_OUTPUT_CHARS
DEFAULT_TIMEOUT = EXEC_DEFAULT_TIMEOUT

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


async def run_exec(command: str, timeout: int = DEFAULT_TIMEOUT, workdir: str | None = None) -> str:
    timeout = min(max(timeout, 1), 120)
    cwd = workdir if workdir and os.path.isdir(workdir) else None

    log.info("exec → %s (timeout=%ds, cwd=%s)", command, timeout, cwd or ".")
    start = time.monotonic()

    # Inject GitHub token so gh/git commands can authenticate
    env = os.environ.copy()
    github_token = get_secrets()["GITHUB_TOKEN"]
    if github_token:
        env["GH_TOKEN"] = github_token
        env["GITHUB_TOKEN"] = github_token

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        elapsed = time.monotonic() - start
        log.warning("exec ✗ timed out after %.1fs: %s", elapsed, command)
        return f"[Timed out after {timeout}s]"

    elapsed = time.monotonic() - start
    output = ""
    if stdout:
        output += stdout.decode(errors="replace")
    if stderr:
        output += ("\n--- stderr ---\n" + stderr.decode(errors="replace"))

    if not output.strip():
        output = f"[No output, exit code {proc.returncode}]"
    elif proc.returncode != 0:
        output += f"\n[exit code {proc.returncode}]"

    truncated = len(output) > MAX_OUTPUT_CHARS
    if truncated:
        output = output[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(output)} chars total]"

    if proc.returncode == 0:
        log.info("exec ✓ exit=0 %.1fs (%d chars%s): %s", elapsed, len(output), " truncated" if truncated else "", command)
    else:
        log.warning("exec ✗ exit=%s %.1fs: %s", proc.returncode, elapsed, command)
    log.debug("exec output:\n%s", output[:500])

    return output
