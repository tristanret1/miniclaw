#!/usr/bin/env python3
"""Debug tool: dump session history by session key.

Usage:
    python debug_history.py <session_key>           # dump messages as JSON
    python debug_history.py <session_key> --pretty   # human-readable format
    python debug_history.py <session_key> --clean    # strip tool calls, text only
    python debug_history.py --list                   # list all session keys
    python debug_history.py <session_key> --last N   # only last N messages
    python debug_history.py --all --clean            # all sessions, text only
    python debug_history.py --all --clean --pretty   # all sessions, text only, readable
    python debug_history.py --purge                  # delete ALL sessions (with confirmation)
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Minimal DB access — avoids importing bot.config (which needs .env / Discord
# token) so the script works standalone.
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
DEFAULT_DB = WORKSPACE_DIR / "sessions.db"

# Load .env so DATABASE_URL is available without importing bot.config
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def _sqlite_load(db_path: Path, session_key: str, limit: int | None = None) -> list[dict]:
    if not db_path.exists():
        print(f"error: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if limit:
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM ("
            "  SELECT id, role, content, created_at FROM messages"
            "  WHERE session_key = ? ORDER BY id DESC LIMIT ?"
            ") ORDER BY id ASC",
            (session_key, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM messages "
            "WHERE session_key = ? ORDER BY id ASC",
            (session_key,),
        ).fetchall()
    conn.close()

    messages = []
    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        messages.append({
            "id": row["id"],
            "role": row["role"],
            "content": content,
            "created_at": row["created_at"],
        })
    return messages


async def _pg_load(session_key: str, limit: int | None = None) -> list[dict]:
    """Load from PostgreSQL (requires DATABASE_URL in env)."""
    import os
    import ssl

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("error: DATABASE_URL not set (needed for --pg mode)", file=sys.stderr)
        sys.exit(1)

    import asyncpg
    ssl_ctx = ssl.create_default_context()
    conn = await asyncpg.connect(url, ssl=ssl_ctx)

    if limit:
        rows = await conn.fetch(
            "SELECT id, role, content, created_at FROM ("
            "  SELECT id, role, content, created_at FROM messages"
            "  WHERE session_key = $1 ORDER BY id DESC LIMIT $2"
            ") sub ORDER BY id ASC",
            session_key, limit,
        )
    else:
        rows = await conn.fetch(
            "SELECT id, role, content, created_at FROM messages "
            "WHERE session_key = $1 ORDER BY id ASC",
            session_key,
        )
    await conn.close()

    messages = []
    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        messages.append({
            "id": row["id"],
            "role": row["role"],
            "content": content,
            "created_at": str(row["created_at"]),
        })
    return messages


def _sqlite_load_all(db_path: Path) -> dict[str, list[dict]]:
    """Load all sessions from SQLite, grouped by session_key."""
    if not db_path.exists():
        print(f"error: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, session_key, role, content, created_at "
        "FROM messages ORDER BY id ASC"
    ).fetchall()
    conn.close()

    sessions: dict[str, list[dict]] = {}
    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        sessions.setdefault(row["session_key"], []).append({
            "id": row["id"],
            "role": row["role"],
            "content": content,
            "created_at": row["created_at"],
        })
    return sessions


async def _pg_load_all() -> dict[str, list[dict]]:
    """Load all sessions from PostgreSQL, grouped by session_key."""
    import os
    import ssl

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("error: DATABASE_URL not set (needed for --pg mode)", file=sys.stderr)
        sys.exit(1)

    import asyncpg
    ssl_ctx = ssl.create_default_context()
    conn = await asyncpg.connect(url, ssl=ssl_ctx)
    rows = await conn.fetch(
        "SELECT id, session_key, role, content, created_at "
        "FROM messages ORDER BY id ASC"
    )
    await conn.close()

    sessions: dict[str, list[dict]] = {}
    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        sessions.setdefault(row["session_key"], []).append({
            "id": row["id"],
            "role": row["role"],
            "content": content,
            "created_at": str(row["created_at"]),
        })
    return sessions


def _list_sessions(db_path: Path) -> None:
    if not db_path.exists():
        print(f"error: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT session_key, COUNT(*) as msg_count, "
        "MIN(created_at) as first_msg, MAX(created_at) as last_msg "
        "FROM messages GROUP BY session_key ORDER BY last_msg DESC"
    ).fetchall()
    conn.close()

    if not rows:
        print("No sessions found.")
        return

    print(f"{'SESSION KEY':<40} {'MSGS':>5}  {'FIRST MESSAGE':<20} {'LAST MESSAGE':<20}")
    print("-" * 90)
    for row in rows:
        print(f"{row['session_key']:<40} {row['msg_count']:>5}  {row['first_msg']:<20} {row['last_msg']:<20}")


async def _list_sessions_pg() -> None:
    import os
    import ssl

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("error: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    import asyncpg
    ssl_ctx = ssl.create_default_context()
    conn = await asyncpg.connect(url, ssl=ssl_ctx)
    rows = await conn.fetch(
        "SELECT session_key, COUNT(*) as msg_count, "
        "MIN(created_at) as first_msg, MAX(created_at) as last_msg "
        "FROM messages GROUP BY session_key ORDER BY last_msg DESC"
    )
    await conn.close()

    if not rows:
        print("No sessions found.")
        return

    print(f"{'SESSION KEY':<40} {'MSGS':>5}  {'FIRST MESSAGE':<20} {'LAST MESSAGE':<20}")
    print("-" * 90)
    for row in rows:
        print(f"{row['session_key']:<40} {row['msg_count']:>5}  {str(row['first_msg']):<20} {str(row['last_msg']):<20}")


# ---------------------------------------------------------------------------
# Clean: strip tool_use / tool_result, keep text only
# ---------------------------------------------------------------------------

def _is_tool_block(block: dict) -> bool:
    """Check if a block is tool_use or tool_result."""
    return isinstance(block, dict) and block.get("type") in ("tool_use", "tool_result")


def _extract_text(content) -> str | None:
    """Extract plain text from any content format. Returns None if no text.

    Handles: str, list[block], dict (single block), and string-encoded JSON
    that is actually tool data.
    """
    # String content — but might be JSON-encoded tool data
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content  # genuinely plain text
        # If it parsed into a list/dict, recurse to check for tool blocks
        return _extract_text(parsed)

    # Single dict block
    if isinstance(content, dict):
        if _is_tool_block(content):
            return None
        if content.get("type") == "text":
            return content.get("text")
        return None

    # List of blocks
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block["text"])
                # skip tool_use, tool_result, image, etc.
            elif isinstance(block, str):
                texts.append(block)
        return "\n".join(texts) if texts else None

    return None


def _clean_messages(messages: list[dict]) -> list[dict]:
    """Strip tool_use/tool_result blocks, keep only text content.

    - user messages containing only tool_result blocks are dropped entirely
    - assistant messages containing only tool_use blocks are dropped entirely
    - mixed messages keep their text blocks only
    - consecutive same-role messages after cleaning are merged
    """
    cleaned = []
    for msg in messages:
        content = msg["content"]
        text = _extract_text(content)
        if text is None:
            continue
        cleaned.append({
            "role": msg["role"],
            "content": text,
        })

    # Merge consecutive same-role messages
    merged = []
    for msg in cleaned:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] += "\n\n" + msg["content"]
        else:
            merged.append(dict(msg))

    return merged


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

def _pretty_print(messages: list[dict]) -> None:
    """Human-readable output."""
    for msg in messages:
        role = msg["role"].upper()
        ts = msg.get("created_at", "")
        print(f"\n{'='*60}")
        print(f"[{role}]  id={msg['id']}  {ts}")
        print("-" * 60)

        content = msg["content"]
        if isinstance(content, str):
            print(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    print(block)
                    continue
                btype = block.get("type", "unknown")
                if btype == "text":
                    print(block.get("text", ""))
                elif btype == "tool_use":
                    print(f"  [tool_use] {block.get('name', '?')} id={block.get('id', '?')}")
                    print(f"  input: {json.dumps(block.get('input', {}), ensure_ascii=False, indent=2)}")
                elif btype == "tool_result":
                    print(f"  [tool_result] tool_use_id={block.get('tool_use_id', '?')}")
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        # Truncate long tool results
                        if len(result_content) > 500:
                            print(f"  {result_content[:500]}... ({len(result_content)} chars)")
                        else:
                            print(f"  {result_content}")
                    else:
                        print(f"  {json.dumps(result_content, ensure_ascii=False, indent=2)}")
                elif btype == "image":
                    src = block.get("source", {})
                    print(f"  [image] {src.get('type', '?')}: {src.get('url', '?')}")
                else:
                    print(f"  [{btype}] {json.dumps(block, ensure_ascii=False)}")
        else:
            print(json.dumps(content, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Purge: delete all sessions
# ---------------------------------------------------------------------------

def _purge_all(db_path: Path) -> None:
    if not db_path.exists():
        print(f"error: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT session_key, COUNT(*) as cnt FROM messages GROUP BY session_key"
    ).fetchall()

    if not rows:
        print("No sessions to delete.")
        conn.close()
        return

    total = sum(r["cnt"] for r in rows)
    print(f"About to delete {len(rows)} sessions ({total} messages total):")
    for r in rows:
        print(f"  {r['session_key']}  ({r['cnt']} msgs)")

    confirm = input("\nType 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        conn.close()
        return

    conn.execute("DELETE FROM messages")
    conn.commit()
    conn.close()
    print(f"Deleted {total} messages from {len(rows)} sessions.")


async def _purge_all_pg() -> None:
    import os
    import ssl

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("error: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    import asyncpg
    ssl_ctx = ssl.create_default_context()
    conn = await asyncpg.connect(url, ssl=ssl_ctx)

    rows = await conn.fetch(
        "SELECT session_key, COUNT(*) as cnt FROM messages GROUP BY session_key"
    )

    if not rows:
        print("No sessions to delete.")
        await conn.close()
        return

    total = sum(r["cnt"] for r in rows)
    print(f"About to delete {len(rows)} sessions ({total} messages total):")
    for r in rows:
        print(f"  {r['session_key']}  ({r['cnt']} msgs)")

    confirm = input("\nType 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        await conn.close()
        return

    result = await conn.execute("DELETE FROM messages")
    await conn.close()
    count = int(result.split()[-1])
    print(f"Deleted {count} messages from {len(rows)} sessions.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Debug session history")
    parser.add_argument("session_key", nargs="?", help="Session key (channel_id:user_id)")
    parser.add_argument("--all", action="store_true", help="Process all sessions")
    parser.add_argument("--list", action="store_true", help="List all session keys")
    parser.add_argument("--pretty", action="store_true", help="Human-readable output")
    parser.add_argument("--clean", action="store_true", help="Strip tool calls, keep text only")
    parser.add_argument("--last", type=int, metavar="N", help="Only show last N messages")
    parser.add_argument("--purge", action="store_true", help="Delete ALL sessions (requires confirmation)")
    parser.add_argument("--sqlite", action="store_true", help="Use SQLite instead of PostgreSQL")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"SQLite DB path (default: {DEFAULT_DB})")
    args = parser.parse_args()

    use_pg = not args.sqlite

    if args.purge:
        if use_pg:
            asyncio.run(_purge_all_pg())
        else:
            _purge_all(args.db)
        return

    if args.list:
        if use_pg:
            asyncio.run(_list_sessions_pg())
        else:
            _list_sessions(args.db)
        return

    # --all: process every session
    if args.all:
        if use_pg:
            all_sessions = asyncio.run(_pg_load_all())
        else:
            all_sessions = _sqlite_load_all(args.db)

        if not all_sessions:
            print("No sessions found.", file=sys.stderr)
            sys.exit(1)

        total_msgs = sum(len(v) for v in all_sessions.values())
        print(f"Loaded {len(all_sessions)} sessions ({total_msgs} messages total)", file=sys.stderr)

        all_output = {}
        for key, messages in all_sessions.items():
            if args.last:
                messages = messages[-args.last:]
            if args.clean:
                messages = _clean_messages(messages)
            if not messages:
                continue

            if args.pretty:
                print(f"\n{'#'*60}")
                print(f"# SESSION: {key}")
                print(f"{'#'*60}")
                _pretty_print(messages)
            else:
                all_output[key] = [{"role": m["role"], "content": m["content"]} for m in messages]

        if not args.pretty:
            print(json.dumps(all_output, ensure_ascii=False, indent=2))

        if args.clean:
            clean_total = sum(len(v) for v in all_output.values()) if not args.pretty else 0
            print(f"\nAfter clean: {clean_total or '?'} messages across all sessions", file=sys.stderr)
        return

    if not args.session_key:
        parser.error("session_key is required (or use --all / --list / --purge)")

    if use_pg:
        messages = asyncio.run(_pg_load(args.session_key, args.last))
    else:
        messages = _sqlite_load(args.db, args.session_key, args.last)

    if not messages:
        print(f"No messages found for session: {args.session_key}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(messages)} messages for session: {args.session_key}", file=sys.stderr)

    if args.clean:
        messages = _clean_messages(messages)
        print(f"After clean: {len(messages)} messages (text only)\n", file=sys.stderr)
    else:
        print(file=sys.stderr)

    if args.pretty:
        _pretty_print(messages)
    else:
        # Output as JSON message list (compatible with Anthropic API format)
        api_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
        print(json.dumps(api_messages, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
