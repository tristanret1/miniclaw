"""Reddit tool — browse, search, and interact via rdt-cli.

Wraps the `rdt` CLI (rdt-cli package) for subreddit browsing, post reading,
searching, and interactions (upvote, save, comment, subscribe).
"""

from __future__ import annotations

import asyncio
import shutil

from bot.logger import get_logger

log = get_logger("reddit")

MAX_OUTPUT = 4000

# rdt-cli may shadow another `rdt` in PATH; find the correct one
_RDT_BIN: str | None = None


def _find_rdt() -> str:
    global _RDT_BIN
    if _RDT_BIN:
        return _RDT_BIN
    import os
    # Prefer the uv-managed rdt-cli
    uv_path = os.path.expanduser("~/.local/bin/rdt")
    if os.path.isfile(uv_path) and os.access(uv_path, os.X_OK):
        _RDT_BIN = uv_path
        return _RDT_BIN
    # Fallback to PATH
    found = shutil.which("rdt")
    _RDT_BIN = found or "rdt"
    return _RDT_BIN


async def _run_rdt(*args: str, timeout: int = 30) -> str:
    """Run an rdt CLI command and return stdout+stderr."""
    rdt = _find_rdt()
    cmd = [rdt, *args]
    log.info("rdt %s", " ".join(args))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = (stdout or b"").decode() + (stderr or b"").decode()
        return output[:MAX_OUTPUT] if output else "(no output)"
    except asyncio.TimeoutError:
        return f"(rdt command timed out after {timeout}s)"
    except FileNotFoundError:
        return "Error: rdt-cli not found. Install with: uv tool install rdt-cli"
    except Exception as e:
        return f"Error running rdt: {e}"


async def run_reddit(action: str, **kwargs) -> str:
    """Execute a Reddit tool action via rdt-cli."""

    # ── Auth / Status ──
    if action == "status":
        return await _run_rdt("status", "--json")

    if action == "whoami":
        return await _run_rdt("whoami")

    # ── Browse ──
    if action == "feed":
        args = ["feed"]
        if kwargs.get("subs_only"):
            args.append("--subs-only")
        if kwargs.get("count"):
            args.extend(["-n", str(kwargs["count"])])
        if kwargs.get("max_subs"):
            args.extend(["--max-subs", str(kwargs["max_subs"])])
        return await _run_rdt(*args)

    if action == "popular":
        args = ["popular"]
        if kwargs.get("full_text"):
            args.append("--full-text")
        return await _run_rdt(*args)

    if action == "all":
        return await _run_rdt("all")

    if action == "sub":
        name = kwargs.get("subreddit", "")
        if not name:
            return "Error: subreddit name is required"
        args = ["sub", name]
        if kwargs.get("sort"):
            args.extend(["-s", kwargs["sort"]])
        if kwargs.get("time_filter"):
            args.extend(["-t", kwargs["time_filter"]])
        return await _run_rdt(*args)

    if action == "sub_info":
        name = kwargs.get("subreddit", "")
        if not name:
            return "Error: subreddit name is required"
        return await _run_rdt("sub-info", name)

    if action == "user":
        username = kwargs.get("username", "")
        if not username:
            return "Error: username is required"
        return await _run_rdt("user", username)

    if action == "user_posts":
        username = kwargs.get("username", "")
        if not username:
            return "Error: username is required"
        return await _run_rdt("user-posts", username)

    if action == "user_comments":
        username = kwargs.get("username", "")
        if not username:
            return "Error: username is required"
        return await _run_rdt("user-comments", username)

    if action == "saved":
        return await _run_rdt("saved")

    if action == "upvoted":
        return await _run_rdt("upvoted")

    # ── Reading ──
    if action == "read":
        post_id = kwargs.get("post_id", "")
        if not post_id:
            return "Error: post_id is required"
        args = ["read", post_id]
        if kwargs.get("expand_more"):
            args.append("--expand-more")
        if kwargs.get("sort"):
            args.extend(["-s", kwargs["sort"]])
        return await _run_rdt(*args, timeout=60)

    if action == "show":
        index = kwargs.get("index")
        if index is None:
            return "Error: index is required (number from last listing)"
        args = ["show", str(index)]
        if kwargs.get("expand_more"):
            args.append("--expand-more")
        if kwargs.get("sort"):
            args.extend(["-s", kwargs["sort"]])
        return await _run_rdt(*args, timeout=60)

    # ── Search ──
    if action == "search":
        query = kwargs.get("query", "")
        if not query:
            return "Error: query is required"
        args = ["search", query]
        if kwargs.get("subreddit"):
            args.extend(["-r", kwargs["subreddit"]])
        if kwargs.get("sort"):
            args.extend(["-s", kwargs["sort"]])
        if kwargs.get("time_filter"):
            args.extend(["-t", kwargs["time_filter"]])
        if kwargs.get("compact"):
            args.append("--compact")
        return await _run_rdt(*args)

    # ── Interactions ──
    if action == "upvote":
        index = kwargs.get("index")
        if index is None:
            return "Error: index is required"
        args = ["upvote", str(index)]
        if kwargs.get("down"):
            args.append("--down")
        if kwargs.get("undo"):
            args.append("--undo")
        return await _run_rdt(*args)

    if action == "save":
        index = kwargs.get("index")
        if index is None:
            return "Error: index is required"
        args = ["save", str(index)]
        if kwargs.get("undo"):
            args.append("--undo")
        return await _run_rdt(*args)

    if action == "subscribe":
        name = kwargs.get("subreddit", "")
        if not name:
            return "Error: subreddit name is required"
        args = ["subscribe", name]
        if kwargs.get("undo"):
            args.append("--undo")
        return await _run_rdt(*args)

    if action == "comment":
        index = kwargs.get("index")
        text = kwargs.get("text", "")
        if index is None:
            return "Error: index is required"
        if not text:
            return "Error: comment text is required"
        return await _run_rdt("comment", str(index), text)

    return (
        f"Error: unknown action '{action}'. Available: "
        "status, whoami, feed, popular, all, sub, sub_info, "
        "user, user_posts, user_comments, saved, upvoted, "
        "read, show, search, upvote, save, subscribe, comment"
    )


# ── Tool schema ──────────────────────────────────────────────────────────────

REDDIT_TOOL = {
    "name": "reddit",
    "description": (
        "Browse and interact with Reddit via rdt-cli. "
        "Browse subreddits, read posts and comments, search, "
        "upvote, save, comment, and subscribe. "
        "Use 'sub' to list posts, then 'show <index>' to read a post from the listing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "status", "whoami",
                    "feed", "popular", "all", "sub", "sub_info",
                    "user", "user_posts", "user_comments", "saved", "upvoted",
                    "read", "show", "search",
                    "upvote", "save", "subscribe", "comment",
                ],
                "description": (
                    "status: check login status (JSON). "
                    "whoami: detailed profile (karma, account age). "
                    "feed: home feed (use subs_only to skip algorithm). "
                    "popular: popular posts. all: /r/all. "
                    "sub: browse a subreddit (with optional sort/time_filter). "
                    "sub_info: subreddit metadata (subscribers, description). "
                    "user: user profile. user_posts: user's submitted posts. "
                    "user_comments: user's comments. "
                    "saved: your saved posts. upvoted: your upvoted posts. "
                    "read: read post by Reddit ID. "
                    "show: read post by index from last listing. "
                    "search: search Reddit globally or within a subreddit. "
                    "upvote/save/subscribe/comment: interactions (require login)."
                ),
            },
            "subreddit": {
                "type": "string",
                "description": "Subreddit name without r/ (for sub, sub_info, search, subscribe).",
            },
            "username": {
                "type": "string",
                "description": "Reddit username (for user, user_posts, user_comments).",
            },
            "query": {
                "type": "string",
                "description": "Search query (for search action).",
            },
            "post_id": {
                "type": "string",
                "description": "Reddit post ID like '1abc123' (for read action).",
            },
            "index": {
                "type": "integer",
                "description": "Result index from last listing (for show, upvote, save, comment).",
            },
            "sort": {
                "type": "string",
                "enum": ["hot", "new", "top", "rising", "controversial", "best"],
                "description": "Sort order (for sub, search, show).",
            },
            "time_filter": {
                "type": "string",
                "enum": ["hour", "day", "week", "month", "year", "all"],
                "description": "Time filter when sort=top (for sub, search).",
            },
            "text": {
                "type": "string",
                "description": "Comment text (for comment action).",
            },
            "count": {
                "type": "integer",
                "description": "Number of posts per subreddit (for feed, with -n flag).",
            },
            "max_subs": {
                "type": "integer",
                "description": "Max subreddits to fetch from (for feed, with --max-subs).",
            },
            "subs_only": {
                "type": "boolean",
                "description": "Subscriptions-only feed, no algorithm (for feed).",
            },
            "full_text": {
                "type": "boolean",
                "description": "Show full titles (for popular).",
            },
            "expand_more": {
                "type": "boolean",
                "description": "Expand 'more comments' (for read, show).",
            },
            "down": {
                "type": "boolean",
                "description": "Downvote instead of upvote (for upvote action).",
            },
            "undo": {
                "type": "boolean",
                "description": "Undo the action (for upvote, save, subscribe).",
            },
            "compact": {
                "type": "boolean",
                "description": "Compact output for agent use (for search).",
            },
        },
        "required": ["action"],
    },
}
