"""Non-configurable platform and protocol constants.

These are fixed values determined by external APIs, platform limits, or
algorithm design — not user preferences. They should never appear in .env.
"""

# ── Discord ───────────────────────────────────────────────────────────────────

DISCORD_MAX_MESSAGE_LENGTH = 2000

# ── Anthropic API ─────────────────────────────────────────────────────────────

ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_BETA_FEATURES = "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# Claude Code identity headers (stealth mode — mimics Claude Code CLI)
CLAUDE_CODE_VERSION = "2.1.75"
CLAUDE_CODE_SYSTEM_PREFIX = "You are Claude Code, Anthropic's official CLI for Claude."

# ── Anthropic OAuth ───────────────────────────────────────────────────────────

ANTHROPIC_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
ANTHROPIC_AUTHORIZATION_URL = "https://claude.ai/oauth/authorize"
ANTHROPIC_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
ANTHROPIC_REDIRECT_URI = "https://platform.claude.com/oauth/code/callback"
ANTHROPIC_SCOPES = (
    "org:create_api_key user:profile user:inference "
    "user:sessions:claude_code user:mcp_servers"
)

# ── Codex (OpenAI) OAuth ──────────────────────────────────────────────────────

CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_ISSUER = "https://auth.openai.com"
CODEX_API_ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"
CODEX_DEVICE_CODE_URL = f"{CODEX_ISSUER}/api/accounts/deviceauth/usercode"
CODEX_DEVICE_TOKEN_URL = f"{CODEX_ISSUER}/api/accounts/deviceauth/token"
CODEX_TOKEN_URL = f"{CODEX_ISSUER}/oauth/token"
CODEX_DEVICE_REDIRECT_URI = f"{CODEX_ISSUER}/deviceauth/callback"
CODEX_DEVICE_AUTH_PAGE = f"{CODEX_ISSUER}/codex/device"

# ── LLM processing ────────────────────────────────────────────────────────────

# Maximum tool-use rounds per streaming response before giving up
MAX_TOOL_ROUNDS = 50

# Maximum tool-use rounds during background auto-flush
MAX_FLUSH_ROUNDS = 5

# Character threshold that triggers background auto-flush (~20k tokens at 4 chars/token)
AUTO_FLUSH_CHAR_THRESHOLD = 80_000

# ── Tool output limits ────────────────────────────────────────────────────────

# Maximum characters returned by exec tool (avoids flooding Discord / Claude context)
TOOL_MAX_OUTPUT_CHARS = 4000

# Maximum characters returned by claude_code (ACP) tool
ACP_MAX_OUTPUT_CHARS = 8000

# Default exec timeout in seconds
EXEC_DEFAULT_TIMEOUT = 30

# ── Memory ────────────────────────────────────────────────────────────────────

# Chunking config (mirrors openclaw defaults)
MEMORY_CHUNK_TOKENS = 400
MEMORY_CHUNK_OVERLAP = 80
MEMORY_CHARS_PER_TOKEN = 4  # rough estimate

# OpenAI embedding model and dimension
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# Hybrid search weights (must sum to 1.0)
BM25_WEIGHT = 0.4
VECTOR_WEIGHT = 0.6

# ── External API URLs ─────────────────────────────────────────────────────────

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/Accounts"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# ── Heartbeat ─────────────────────────────────────────────────────────────────

# Sentinel token: if LLM response contains only this, discard without notifying user
HEARTBEAT_TOKEN = "HEARTBEAT_OK"

# ── Skills ────────────────────────────────────────────────────────────────────

# Maximum SKILL.md file size in bytes (256 KB, same as openclaw)
MAX_SKILL_FILE_BYTES = 256_000
