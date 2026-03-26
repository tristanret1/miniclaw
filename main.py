import sys
from pathlib import Path

# Delegate to agent CLI if "agents" subcommand is used
if len(sys.argv) > 1 and sys.argv[1] == "agents":
    from scripts.agent_cli import main as cli_main
    cli_main(sys.argv[2:])
    sys.exit(0)

# Parse --only flag for selective agent startup
_only_agents: list[str] | None = None
_voice_only = "--voice-only" in sys.argv
for i, arg in enumerate(sys.argv[1:], 1):
    if arg == "--only" and i + 1 < len(sys.argv):
        _only_agents = [n.strip() for n in sys.argv[i + 1].split(",") if n.strip()]
        break
    if arg.startswith("--only="):
        _only_agents = [n.strip() for n in arg.split("=", 1)[1].split(",") if n.strip()]
        break

env_path = Path(__file__).parent / ".env"
creds_path = Path(__file__).parent / ".credentials.json"

if not env_path.exists() or not creds_path.exists():
    print("First run — starting setup...\n")
    from setup import main as run_setup
    run_setup()
    print()

import asyncio
from bot.config import SMS_ENABLED, IMESSAGE_ENABLED, VOICE_ENABLED
from bot.agent import load_agents
from bot.client import create_bot
from bot.session import SessionManager


async def main():
    # Initialize PostgreSQL pool + schema if DATABASE_URL is set
    from bot import db
    if db.use_postgres():
        await db.ensure_schema()
        print("Using PostgreSQL backend (Neon)")
    else:
        print("Using SQLite backend (local)")

    agents = load_agents(only=_only_agents)
    print(f"Starting {len(agents)} agent(s): {', '.join(a.name for a in agents)}")

    # Initialize per-agent runtime state
    for agent in agents:
        agent.session_mgr = SessionManager(db_path=agent.sessions_db)

    tasks = []

    if _voice_only:
        # Voice-only mode — skip Discord bots and other gateways
        from bot.voice_gateway import start_voice_gateway
        tasks.append(start_voice_gateway())
        print("Voice-only mode — Discord bots skipped")
    else:
        for agent in agents:
            bot = create_bot(agent)
            tasks.append(bot.start(agent.discord_token))

        if SMS_ENABLED:
            from bot.sms_gateway import start_sms_server
            tasks.append(start_sms_server())

        if IMESSAGE_ENABLED:
            from bot.imessage_gateway import start_imessage_gateway
            tasks.append(start_imessage_gateway())

        if VOICE_ENABLED:
            from bot.voice_gateway import start_voice_gateway
            tasks.append(start_voice_gateway())

    try:
        await asyncio.gather(*tasks)
    finally:
        from bot.acp import shutdown
        await shutdown()
        await db.close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
