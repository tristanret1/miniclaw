# Kimi Provider Support

**Date:** 2026-04-21
**Status:** Approved

## Goal

Add Kimi (Moonshot AI, 月之暗面) as a fifth LLM provider option alongside `anthropic`, `codex`, `glm`, and `minimax`. Selectable via `config.yaml` → `llm.provider: kimi`.

## Context

Kimi exposes an OpenAI-compatible chat completions API. The existing `OpenAICompatProvider` base class (`bot/provider/openai_compat.py`) already handles the wire format — SSE streaming, function calling, image input, tool result conversion. Adding Kimi is a 5-file change that mirrors `GLMProvider`.

No changes to `base.py`, `openai_compat.py`, `processor.py`, or `llm.py`. No new abstractions.

## API details

- **Endpoint:** `https://api.moonshot.cn/v1/chat/completions` (China region, per user choice)
- **Auth:** `Authorization: Bearer $KIMI_API_KEY`
- **Default model:** `kimi-latest` (overridable via `config.yaml`)
- **Body format:** standard OpenAI `max_tokens` — no provider-specific quirks (unlike MiniMax's `max_completion_tokens`)
- **Vision:** supports OpenAI-style `image_url` blocks → works unmodified via existing `to_openai_messages`

## Changes

### 1. `bot/provider/kimi.py` (new, ~10 lines)

```python
"""Kimi provider — Moonshot AI chat completions with tool calling."""

from bot.provider.openai_compat import OpenAICompatProvider


class KimiProvider(OpenAICompatProvider):
    ENV_KEY = "KIMI_API_KEY"

    def __init__(self, model: str):
        super().__init__(model)
        from bot.config import get_config
        self.API_URL = get_config().llm.kimi.api_url
```

### 2. `bot/config_schema.py`

- Add `KimiConfig` dataclass with defaults `model="kimi-latest"`, `api_url="https://api.moonshot.cn/v1/chat/completions"`
- Add `kimi: KimiConfig` field to `LLMConfig` (with default_factory)
- Wire `KimiConfig.from_dict` in `LLMConfig.from_dict`

### 3. `bot/provider/__init__.py`

- Import `KimiProvider`
- Add `"kimi": KimiProvider` to `_PROVIDERS` registry
- Add `if provider == "kimi": return get_provider("kimi", cfg.llm.kimi.model)` branch in `get_default_provider()`
- Export `KimiProvider` in `__all__`

### 4. `config.yaml`

Add under `llm:` block (do NOT change the existing `provider: minimax` default):

```yaml
  kimi:
    model: kimi-latest
    api_url: https://api.moonshot.cn/v1/chat/completions
```

### 5. `.env.example`

Add commented line near other optional API keys:

```
# Optional — Kimi (Moonshot AI, 月之暗面) API key
# KIMI_API_KEY=xxx
```

### 6. `tests/provider/test_registry.py` (small update)

Add a test ensuring `get_provider("kimi", "kimi-latest")` returns a `KimiProvider` instance with the right model. No end-to-end HTTP test (matches existing coverage depth for GLM/MiniMax).

## Failure modes

- **Missing `KIMI_API_KEY`:** `_get_api_key()` raises `RuntimeError("KIMI_API_KEY not set in environment")` on first request. Same failure mode as GLM/MiniMax.
- **Invalid model name / 4xx from Kimi:** existing `OpenAICompatProvider` error path surfaces the HTTP status and response body.
- **Auth expired / 401:** raised as `"Auth failed — check API key"`. API-key providers have no refresh flow (unlike Anthropic/Codex OAuth).

## Out of scope

- Dedicated `test_kimi.py` with full stream-parse tests — GLM has no such file either; the shared `openai_compat` path is covered by `test_transform.py` and existing provider tests.
- Changing the default `llm.provider` — stays at `minimax`.
- Kimi-specific tool-calling quirks — none known; revisit if real-world usage surfaces issues.
- Any UI/CLI surfacing of the new provider choice beyond editing `config.yaml`.
