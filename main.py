import sys
from pathlib import Path

# Delegate to agent CLI if "agents" subcommand is used
if len(sys.argv) > 1 and sys.argv[1] == "agents":
    from scripts.agent_cli import main as cli_main
    cli_main(sys.argv[2:])
    sys.exit(0)

# Parse CLI flags
_only_agents: list[str] | None = None
_only_gateways: set[str] | None = None  # e.g. {"feishu", "sms"}
_voice_only = "--voice-only" in sys.argv
for i, arg in enumerate(sys.argv[1:], 1):
    if arg == "--only" and i + 1 < len(sys.argv):
        _only_agents = [n.strip() for n in sys.argv[i + 1].split(",") if n.strip()]
    elif arg.startswith("--only="):
        _only_agents = [n.strip() for n in arg.split("=", 1)[1].split(",") if n.strip()]
    elif arg == "--gateway" and i + 1 < len(sys.argv):
        _only_gateways = {n.strip() for n in sys.argv[i + 1].split(",") if n.strip()}
    elif arg.startswith("--gateway="):
        _only_gateways = {n.strip() for n in arg.split("=", 1)[1].split(",") if n.strip()}

env_path = Path(__file__).parent / ".env"
creds_path = Path(__file__).parent / ".credentials.json"

if not env_path.exists() or not creds_path.exists():
    print("First run — starting setup...\n")
    from setup import main as run_setup
    run_setup()
    print()

import asyncio
from bot.config import get_config
from bot.agent import load_agents_async
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

    agents = await load_agents_async(only=_only_agents)
    print(f"Starting {len(agents)} agent(s): {', '.join(a.name for a in agents)}")

    # Initialize per-agent runtime state
    for agent in agents:
        agent.session_mgr = SessionManager(db_path=agent.sessions_db)

    tasks = []

    # Find the voice agent (if any)
    voice_agent = next((a for a in agents if a.name == "voice"), None)

    def _gw_enabled(name: str) -> bool:
        """Check if a gateway should start (respects --gateway filter)."""
        if _only_gateways is not None:
            return name in _only_gateways
        return True

    if _voice_only:
        # Voice-only mode — skip Discord bots and other gateways
        from bot.gateway.voice import start_voice_gateway
        tasks.append(start_voice_gateway(agent=voice_agent))
        print(f"Voice-only mode (agent={voice_agent.name if voice_agent else 'default'})")
    elif _only_gateways is not None:
        # Gateway-only mode — skip Discord bots, start only specified gateways
        _gw_cfg = get_config().gateway
        gw_names = []

        if _gw_enabled("feishu") and _gw_cfg.feishu.enabled:
            from bot.gateway.feishu import start_feishu_gateway
            tasks.append(start_feishu_gateway())
            gw_names.append("feishu")

        if _gw_enabled("sms") and _gw_cfg.sms.enabled:
            from bot.gateway.sms import start_sms_server
            tasks.append(start_sms_server())
            gw_names.append("sms")

        if _gw_enabled("imessage") and _gw_cfg.imessage.enabled:
            from bot.gateway.imessage import start_imessage_gateway
            tasks.append(start_imessage_gateway())
            gw_names.append("imessage")

        if _gw_enabled("voice") and _gw_cfg.voice.enabled:
            from bot.gateway.voice import start_voice_gateway
            tasks.append(start_voice_gateway(agent=voice_agent))
            gw_names.append("voice")

        if _gw_enabled("whatsapp") and _gw_cfg.whatsapp.enabled:
            from bot.gateway.whatsapp import start_whatsapp_gateway
            tasks.append(start_whatsapp_gateway())
            gw_names.append("whatsapp")

        if _gw_enabled("api") and _gw_cfg.api.enabled:
            from bot.gateway.api import start_api_server
            tasks.append(start_api_server())
            gw_names.append("api")

        print(f"Gateway-only mode: {', '.join(gw_names) or 'none matched'}")
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

        if _gw_cfg.feishu.enabled:
            from bot.gateway.feishu import start_feishu_gateway
            tasks.append(start_feishu_gateway())

        if _gw_cfg.whatsapp.enabled:
            from bot.gateway.whatsapp import start_whatsapp_gateway
            tasks.append(start_whatsapp_gateway())

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
