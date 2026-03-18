from pathlib import Path

env_path = Path(__file__).parent / ".env"
creds_path = Path(__file__).parent / ".credentials.json"

if not env_path.exists() or not creds_path.exists():
    print("First run — starting setup...\n")
    from setup import main as run_setup
    run_setup()
    print()

import asyncio
import signal
from bot.config import DISCORD_BOT_TOKEN
from bot.client import bot


async def main():
    if not DISCORD_BOT_TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN not set. Run: python setup.py")
    try:
        await bot.start(DISCORD_BOT_TOKEN)
    finally:
        from bot.acp import shutdown
        await shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
