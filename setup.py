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


def setup_codex():
    print("\n── Codex Authorization (uses your ChatGPT subscription) ──")
    from bot.codex_oauth import authorize_headless
    authorize_headless()


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


def write_env(discord_token: str, provider: str):
    lines = [
        f"DISCORD_BOT_TOKEN={discord_token}",
        f"PROVIDER={provider}",
        f"MAX_HISTORY=20",
    ]
    if provider == "anthropic":
        lines.append("CLAUDE_MODEL=claude-sonnet-4-20250514")
    elif provider == "codex":
        lines.append("CODEX_MODEL=gpt-5.3-codex")
    content = "\n".join(lines) + "\n"
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

    # Step 1: Choose provider
    print("\nChoose LLM provider:")
    print("  1. Claude (Anthropic OAuth — uses Claude subscription)")
    print("  2. Codex (OpenAI OAuth — uses ChatGPT Pro/Plus subscription)")
    print("  3. Both (set up both, choose active provider in .env)")
    choice = input("\nEnter choice [1/2/3]: ").strip()

    provider = "anthropic"
    if choice in ("1", "3"):
        setup_claude()
    if choice in ("2", "3"):
        setup_codex()
        if choice == "2":
            provider = "codex"
    if choice == "3":
        provider = input("\nDefault provider? [anthropic/codex]: ").strip() or "anthropic"

    # Step 2: Discord
    # discord_token = setup_discord()
    # write_env(discord_token, provider)

    print("\nSetup complete! Run: python main.py")


if __name__ == "__main__":
    main()
