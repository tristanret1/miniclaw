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
from bot.config import get_config
from bot.agent import load_agents
from bot.client import create_bot
from bot.storage.session import SessionManager


async def main():
    # Initialize PostgreSQL pool + schema if DATABASE_URL is set
    from bot.storage import db
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

    # Find the voice agent (if any)
    voice_agent = next((a for a in agents if a.name == "voice"), None)

    if _voice_only:
        # Voice-only mode — skip Discord bots and other gateways
        from bot.gateway.voice import start_voice_gateway
        tasks.append(start_voice_gateway(agent=voice_agent))
        print(f"Voice-only mode (agent={voice_agent.name if voice_agent else 'default'})")
    else:
        for agent in agents:
            # Skip voice-only agents (no Discord token)
            if not agent.discord_token:
                continue
            bot = create_bot(agent)
            tasks.append(bot.start(agent.discord_token))

        _gw_cfg = get_config().gateway

        if _gw_cfg.api.enabled:
            from bot.gateway.api import start_api_server, get_tracker
            tracker = get_tracker()
            for agent in agents:
                if agent.discord_token:
                    tracker.on_online(agent.name)
            tasks.append(start_api_server())

        if _gw_cfg.sms.enabled:
            from bot.gateway.sms import start_sms_server
            tasks.append(start_sms_server())

        if _gw_cfg.imessage.enabled:
            from bot.gateway.imessage import start_imessage_gateway
            tasks.append(start_imessage_gateway())

        if _gw_cfg.voice.enabled:
            from bot.gateway.voice import start_voice_gateway
            tasks.append(start_voice_gateway(agent=voice_agent))

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
