"""Interactive setup: OAuth login + Discord token → .env"""

import os
import webbrowser
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"
DISCORD_DEV_URL = "https://discord.com/developers/applications"


def setup_claude():
    print("\n── Claude Authorization (uses your Claude subscription) ──\n")
    from bot.oauth import authorize
    authorize()


def setup_discord() -> str:
    print("\n── Discord Bot Token ──")
    print(f"1. Opening {DISCORD_DEV_URL}")
    print("2. Create an application (or select existing)")
    print("3. Go to 'Bot' tab → 'Reset Token' → copy the token")
    print("4. Enable 'Message Content Intent' under Privileged Gateway Intents")
    print("5. Go to 'OAuth2' → 'URL Generator' → select 'bot' scope")
    print("   → select permissions: Send Messages, Read Message History")
    print("   → use the generated URL to invite the bot to your server")
    webbrowser.open(DISCORD_DEV_URL)
    token = input("\nPaste your Discord Bot Token: ").strip()
    if not token:
        raise SystemExit("Bot token cannot be empty.")
    return token


def write_env(discord_token: str):
    content = (
        f"DISCORD_BOT_TOKEN={discord_token}\n"
        f"CLAUDE_MODEL=claude-sonnet-4-20250514\n"
        f"MAX_HISTORY=20\n"
        f"SYSTEM_PROMPT=You are a helpful assistant.\n"
    )
    ENV_PATH.write_text(content)
    os.chmod(ENV_PATH, 0o600)
    print(f"\n.env written to {ENV_PATH}")


def main():
    print("=== MiniClaw Setup ===")

    if ENV_PATH.exists():
        overwrite = input(".env already exists. Overwrite? [y/N] ").strip().lower()
        if overwrite != "y":
            print("Setup cancelled.")
            return

    # Step 1: Claude OAuth
    setup_claude()

    # Step 2: Discord
    discord_token = setup_discord()
    write_env(discord_token)

    print("\nSetup complete! Run: python main.py")


if __name__ == "__main__":
    main()
