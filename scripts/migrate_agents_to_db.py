"""One-time migration: read current workspace files + agents.json and insert into PostgreSQL."""

import asyncio
import json
import os
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

PROJECT_ROOT = Path(__file__).parent.parent


async def migrate():
    import asyncpg

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print("DATABASE_URL not set. Exiting.")
        return

    ssl_ctx = ssl.create_default_context()
    conn = await asyncpg.connect(database_url, ssl=ssl_ctx)

    try:
        from bot.storage.db import ensure_schema
        await ensure_schema()

        agents_json = PROJECT_ROOT / "agents.json"
        if agents_json.exists():
            with open(agents_json) as f:
                data = json.load(f)
            entries = data.get("agents", [])
        else:
            entries = [{
                "name": "default",
                "discord_token": os.getenv("DISCORD_BOT_TOKEN", ""),
                "workspace": "workspace",
                "enabled": True,
            }]

        for entry in entries:
            name = entry.get("name", "default")
            workspace = entry.get("workspace", "workspace")
            workspace_path = Path(workspace)
            if not workspace_path.is_absolute():
                workspace_path = PROJECT_ROOT / workspace_path

            existing = await conn.fetchval("SELECT id FROM agents WHERE name = $1", name)
            if existing:
                print(f"Agent '{name}' already exists in DB, skipping.")
                continue

            soul = identity = user_doc = ""
            for filename, attr in [("SOUL.md", "soul"), ("IDENTITY.md", "identity"), ("USER.md", "user_doc")]:
                filepath = workspace_path / filename
                if filepath.exists():
                    content = filepath.read_text().strip()
                    if attr == "soul": soul = content
                    elif attr == "identity": identity = content
                    else: user_doc = content

            config = {
                "discord": {"bot_token": entry.get("discord_token", "")},
                "llm": {"provider": entry.get("provider", "anthropic")},
            }
            if entry.get("model"):
                provider = config["llm"]["provider"]
                config["llm"][provider] = {"model": entry["model"]}

            # Parse display_name and emoji from IDENTITY.md
            display_name = name
            emoji = ""
            for line in identity.split("\n"):
                if "**Name:**" in line:
                    display_name = line.split("**Name:**")[1].strip()
                elif "**Emoji:**" in line:
                    emoji = line.split("**Emoji:**")[1].strip()

            agent_id = await conn.fetchval(
                """INSERT INTO agents (name, display_name, emoji, config, enabled)
                   VALUES ($1, $2, $3, $4::jsonb, $5) RETURNING id""",
                name, display_name, emoji, json.dumps(config), entry.get("enabled", True),
            )

            for doc_type, content in [("soul", soul), ("identity", identity), ("user_doc", user_doc)]:
                await conn.execute(
                    """INSERT INTO agent_documents (agent_id, doc_type, content, version, message, created_by)
                       VALUES ($1, $2, $3, 1, 'migrated from workspace files', 'migration')""",
                    agent_id, doc_type, content,
                )

            print(f"Migrated agent '{name}' (display={display_name}, emoji={emoji})")

    finally:
        await conn.close()

    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
