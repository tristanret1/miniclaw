import sys
from pathlib import Path

# Delegate to KB CLI if "kb" subcommand is used
if len(sys.argv) > 1 and sys.argv[1] == "kb":
    import asyncio as _asyncio

    async def _kb_cli():
        args = sys.argv[2:]
        if not args:
            print("Usage: main.py kb <ingest|query|list|status|compile> [args]")
            return
        action = args[0]
        from bot.services import kb
        if action == "ingest" and len(args) > 1:
            print(await kb.ingest(args[1], source_type=args[2] if len(args) > 2 else "auto"))
        elif action == "query" and len(args) > 1:
            print(await kb.query(" ".join(args[1:])))
        elif action == "list":
            print(kb.list_kb())
        elif action == "status":
            print(kb.status())
        elif action == "compile":
            print(await kb.compile())
        else:
            print(f"Unknown kb command: {action}")
            print("Usage: main.py kb <ingest|query|list|status|compile> [args]")

    _asyncio.run(_kb_cli())
    sys.exit(0)

_voice_only = "--voice-only" in sys.argv

env_path = Path(__file__).parent / ".env"
creds_path = Path(__file__).parent / ".credentials.json"

if not env_path.exists() or not creds_path.exists():
    print("First run — starting setup...\n")
    from setup import main as run_setup
    run_setup()
    print()

import asyncio
from bot.config import get_config
from bot.agent import load_agent
from bot.storage.session import SessionManager
from bot.logger import get_logger

log = get_logger("main")


async def main():
    # Initialize PostgreSQL pool + schema if DATABASE_URL is set
    from bot.storage import db
    if db.use_postgres():
        await db.ensure_schema()
        print("Using PostgreSQL backend (Neon)")
    else:
        print("Using SQLite backend (local)")

    agent = load_agent()
    agent.session_mgr = SessionManager(db_path=agent.sessions_db)
    print(f"Agent: {agent.name}")

    tasks = []
    _cfg = get_config()
    _gw_cfg = _cfg.gateway

    # Start browser display server (Xvfb + VNC + noVNC — Linux only)
    try:
        from bot.tools.browser_server import start_browser_server
        vnc_url = await start_browser_server()
        if vnc_url:
            print(f"Browser VNC: {vnc_url}")
    except Exception as e:
        log.warning("browser server failed to start: %s", e)

    # Start cron scheduler
    if _cfg.services.cron.enabled:
        from bot.services.cron import get_scheduler
        scheduler = get_scheduler()
        await scheduler.start(None)
        print("Cron scheduler started")

    # Setup gateway with single agent
    from bot.gateway import Gateway, set_gateway
    gateway = Gateway(agent)
    set_gateway(gateway)

    # Start heartbeat
    hb_cfg = _gw_cfg.heartbeat
    if hb_cfg.enabled and hb_cfg.channel_id:
        from bot.channel.heartbeat import HeartbeatRunner
        runner = HeartbeatRunner(
            agent=agent,
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
        tasks.append(start_voice_gateway(agent=agent))
        print("Voice-only mode")
    else:
        # Register Discord adapter
        from bot.channel.discord import DiscordAdapter
        discord_adapter = DiscordAdapter()
        gateway.register_adapter(discord_adapter)
        await discord_adapter.start(gateway)
        tasks.append(discord_adapter.run(agent.discord_token))

        # Register SMS adapter
        if _gw_cfg.sms.enabled:
            from bot.channel.sms import SMSAdapter
            gateway.register_adapter(SMSAdapter())

        # Start gateway (starts non-Discord adapters like SMS)
        async def _run_gateway():
            await gateway.start()
            try:
                await asyncio.Event().wait()
            finally:
                await gateway.stop()
        tasks.append(_run_gateway())

        # API server
        if _gw_cfg.api.enabled:
            from bot.channel.api import start_api_server
            tasks.append(start_api_server())

        # Voice
        if _gw_cfg.voice.enabled:
            from bot.channel.voice import start_voice_gateway
            tasks.append(start_voice_gateway(agent=agent))

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
