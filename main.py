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
from bot.config import get_config, PROJECT_ROOT
from bot.agent import Agent, load_agents_async
from bot.storage.session import SessionManager


def _setup_gateway(agents: list[Agent], gw_cfg, only: set[str] | None = None):
    """Create and configure the Gateway exchange with adapters + agents."""
    from bot.gateway import Gateway, set_gateway

    gateway = Gateway()

    # Register all loaded agents
    for agent in agents:
        gateway.register_agent(agent.name, agent)

    # Register feishu agent from workspace if not already in agents list
    if gw_cfg.feishu.enabled and gw_cfg.feishu.agent:
        agent_name = gw_cfg.feishu.agent
        if agent_name not in {a.name for a in agents}:
            ws = PROJECT_ROOT / f"workspace_{agent_name}"
            ws.mkdir(parents=True, exist_ok=True)
            feishu_agent = Agent(
                name=agent_name,
                discord_token="",
                workspace_dir=ws,
                model="claude-opus-4-6",
            )
            feishu_agent.session_mgr = SessionManager(db_path=feishu_agent.sessions_db)
            gateway.register_agent(agent_name, feishu_agent)

    # Default agent fallback
    default_agent = next((a for a in agents if a.name == "default"), agents[0] if agents else None)
    if default_agent and "default" not in {a.name for a in agents}:
        gateway.register_agent("default", default_agent)

    def _enabled(name: str) -> bool:
        if only is not None:
            return name in only
        return True

    # Register channel adapters
    if _enabled("feishu") and gw_cfg.feishu.enabled:
        from bot.channel.feishu import FeishuAdapter
        gateway.register_adapter(FeishuAdapter())
        gateway.set_channel_agent("feishu", gw_cfg.feishu.agent or "default")

    if _enabled("sms") and gw_cfg.sms.enabled:
        from bot.channel.sms import SMSAdapter
        gateway.register_adapter(SMSAdapter())
        gateway.set_channel_agent("sms", gw_cfg.sms.agent or "default")

    set_gateway(gateway)
    return gateway


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
    _gw_cfg = get_config().gateway
    voice_agent = next((a for a in agents if a.name == "voice"), None)

    # Start browser display server (Xvfb + VNC + noVNC — Linux only)
    try:
        from bot.tools.browser_server import start_browser_server
        vnc_url = await start_browser_server()
        if vnc_url:
            print(f"Browser VNC: {vnc_url}")
    except Exception as e:
        log.warning("browser server failed to start: %s", e)

    # Start cron scheduler (independent of any channel)
    _cfg = get_config()
    if _cfg.services.cron.enabled:
        from bot.services.cron import get_scheduler
        scheduler = get_scheduler()
        await scheduler.start(None)
        print("Cron scheduler started")

    # Start heartbeat (independent of any channel — delivers through gateway)
    hb_cfg = _gw_cfg.heartbeat
    if hb_cfg.enabled and hb_cfg.channel_id:
        from bot.channel.heartbeat import HeartbeatRunner
        default_agent = agents[0] if agents else None
        if default_agent:
            runner = HeartbeatRunner(
                agent=default_agent,
                delivery_channel="discord",
                channel_id=str(hb_cfg.channel_id),
                interval=hb_cfg.interval,
                active_hours_start=hb_cfg.active_start,
                active_hours_end=hb_cfg.active_end,
                active_hours_tz=hb_cfg.active_tz,
                ack_max_chars=hb_cfg.ack_max_chars,
                isolated_session=hb_cfg.isolated,
            )
            await runner.start()
            print(f"Heartbeat started (every {hb_cfg.interval})")

    if _voice_only:
        from bot.channel.voice import start_voice_gateway
        tasks.append(start_voice_gateway(agent=voice_agent))
        print(f"Voice-only mode (agent={voice_agent.name if voice_agent else 'default'})")
    elif _only_gateways is not None:
        # Gateway-only mode — use Gateway exchange
        gateway = _setup_gateway(agents, _gw_cfg, only=_only_gateways)

        if gateway._adapters:
            async def _run_gateway():
                await gateway.start()
                try:
                    await asyncio.Event().wait()
                finally:
                    await gateway.stop()
            tasks.append(_run_gateway())

        # Non-adapter gateways (not yet migrated to adapter pattern)
        if "imessage" in _only_gateways and _gw_cfg.imessage.enabled:
            from bot.channel.imessage import start_imessage_gateway
            tasks.append(start_imessage_gateway())

        if "voice" in _only_gateways and _gw_cfg.voice.enabled:
            from bot.channel.voice import start_voice_gateway
            tasks.append(start_voice_gateway(agent=voice_agent))

        if "api" in _only_gateways and _gw_cfg.api.enabled:
            from bot.channel.api import start_api_server
            tasks.append(start_api_server())

        adapter_names = list(gateway._adapters.keys())
        other = [n for n in ["imessage", "voice", "api"] if n in _only_gateways]
        print(f"Gateway-only mode: {', '.join(adapter_names + other) or 'none matched'}")
    else:
        # Full mode — Discord bots + Gateway exchange + legacy gateways
        gateway = _setup_gateway(agents, _gw_cfg)

        # Register Discord adapters (all of them — gateway picks first ready one for delivery)
        from bot.channel.discord import DiscordAdapter
        for agent in agents:
            if not agent.discord_token:
                continue
            discord_adapter = DiscordAdapter(agent)
            gateway.register_adapter(discord_adapter)
            gateway.set_channel_agent("discord", agent.name)
            await discord_adapter.start(gateway)
            tasks.append(discord_adapter.run(agent.discord_token))

        if gateway._adapters:
            async def _run_gateway():
                await gateway.start()
                try:
                    await asyncio.Event().wait()
                finally:
                    await gateway.stop()
            tasks.append(_run_gateway())

        if _gw_cfg.api.enabled:
            from bot.channel.api import start_api_server, get_tracker
            tracker = get_tracker()
            for agent in agents:
                if agent.discord_token:
                    tracker.on_online(agent.name)
            tasks.append(start_api_server())

        if _gw_cfg.imessage.enabled:
            from bot.channel.imessage import start_imessage_gateway
            tasks.append(start_imessage_gateway())

        if _gw_cfg.voice.enabled:
            from bot.channel.voice import start_voice_gateway
            tasks.append(start_voice_gateway(agent=voice_agent))

    try:
        await asyncio.gather(*tasks)
    finally:
        from bot.acp import shutdown
        await shutdown()
        try:
            from bot.tools.browser import close_browser
            from bot.tools.browser_server import stop_browser_server
            await close_browser()
            stop_browser_server()
        except Exception:
            pass
        from bot.storage import db
        await db.close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
