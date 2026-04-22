# Kimi Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `kimi` (Moonshot AI) as a fifth provider selectable via `config.yaml` → `llm.provider: kimi`.

**Architecture:** Mirror the existing `GLMProvider` — a thin subclass of `OpenAICompatProvider` reading its endpoint from `cfg.llm.kimi.api_url`. No changes to the shared OpenAI-compat wire layer, processor, or llm.py.

**Tech Stack:** Python 3.13, httpx, pytest, pytest-asyncio. Kimi China endpoint `https://api.moonshot.cn/v1/chat/completions`, auth via `KIMI_API_KEY` bearer token, OpenAI-compatible chat completions with streaming and function calling.

**Spec:** `docs/superpowers/specs/2026-04-21-kimi-provider-design.md`

---

## File Structure

**Create:**
- `bot/provider/kimi.py` — `KimiProvider(OpenAICompatProvider)` (~10 lines)

**Modify:**
- `bot/config_schema.py` — add `KimiConfig` dataclass, wire into `LLMConfig`
- `bot/provider/__init__.py` — register `"kimi"` in `_PROVIDERS`, add kimi branch in `get_default_provider()`, export `KimiProvider`
- `config.yaml` — add `kimi:` section under `llm:` (default provider stays `minimax`)
- `.env.example` — add commented `# KIMI_API_KEY=xxx`
- `tests/provider/test_registry.py` — add `test_get_kimi_provider` and `test_get_default_provider_kimi`

---

## Task 1: Add `KimiConfig` to config schema

**Files:**
- Modify: `bot/config_schema.py:89-108` (after `MinimaxConfig`) and `LLMConfig` (lines 102-124)

**Rationale:** The `KimiProvider` reads `get_config().llm.kimi.api_url` in its constructor, so `KimiConfig` must exist on `LLMConfig` before any test can instantiate the provider. This task is a prerequisite for Task 2.

No standalone test — existing project has no direct tests for sub-config dataclasses; coverage is exercised implicitly by the registry tests in Task 2/3.

- [ ] **Step 1: Add `KimiConfig` dataclass**

In `bot/config_schema.py`, directly after the `MinimaxConfig` class (ends around line 99), insert:

```python
@dataclass
class KimiConfig:
    model: str = "kimi-latest"
    api_url: str = "https://api.moonshot.cn/v1/chat/completions"

    @classmethod
    def from_dict(cls, d: dict) -> KimiConfig:
        return cls(
            model=_str(d.get("model"), "kimi-latest"),
            api_url=_str(d.get("api_url"), "https://api.moonshot.cn/v1/chat/completions"),
        )
```

- [ ] **Step 2: Add `kimi` field to `LLMConfig`**

In `LLMConfig` (around line 102-124), add the `kimi` field alongside the others. The resulting class body should read:

```python
@dataclass
class LLMConfig:
    provider: str = "anthropic"
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    codex: CodexConfig = field(default_factory=CodexConfig)
    glm: GLMConfig = field(default_factory=GLMConfig)
    minimax: MinimaxConfig = field(default_factory=MinimaxConfig)
    kimi: KimiConfig = field(default_factory=KimiConfig)
    max_history: int = 25
    max_tokens: int = 4096
    tools_enabled: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> LLMConfig:
        return cls(
            provider=_str(d.get("provider"), "anthropic"),
            anthropic=AnthropicConfig.from_dict(d.get("anthropic") or {}),
            codex=CodexConfig.from_dict(d.get("codex") or {}),
            glm=GLMConfig.from_dict(d.get("glm") or {}),
            minimax=MinimaxConfig.from_dict(d.get("minimax") or {}),
            kimi=KimiConfig.from_dict(d.get("kimi") or {}),
            max_history=_int(d.get("max_history"), 25),
            max_tokens=_int(d.get("max_tokens"), 4096),
            tools_enabled=_bool(d.get("tools_enabled"), False),
        )
```

- [ ] **Step 3: Verify existing tests still pass**

Run: `uv run pytest tests/provider/test_registry.py -v`
Expected: all existing tests pass (adding an optional field with a default factory should not break anything).

- [ ] **Step 4: Commit**

```bash
git add bot/config_schema.py
git commit -m "feat(config): add KimiConfig dataclass to LLMConfig"
```

---

## Task 2: Write failing registry test, then implement `KimiProvider`

**Files:**
- Test: `tests/provider/test_registry.py` (add new tests)
- Create: `bot/provider/kimi.py`
- Modify: `bot/provider/__init__.py`

- [ ] **Step 1: Write the failing test for `get_provider("kimi", ...)`**

Open `tests/provider/test_registry.py`. At the top, add the import line:

```python
from bot.provider.kimi import KimiProvider
```

Inside `class TestProviderRegistry:`, add this test method after `test_get_codex_provider`:

```python
    def test_get_kimi_provider(self):
        provider = get_provider("kimi", "kimi-latest")
        assert isinstance(provider, KimiProvider)
        assert provider.model == "kimi-latest"
        assert provider.API_URL == "https://api.moonshot.cn/v1/chat/completions"
        assert provider.ENV_KEY == "KIMI_API_KEY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/provider/test_registry.py::TestProviderRegistry::test_get_kimi_provider -v`
Expected: FAIL — collection error `ModuleNotFoundError: No module named 'bot.provider.kimi'` (the import at the top of the test file fails).

- [ ] **Step 3: Create `bot/provider/kimi.py`**

Create the file with exactly this content:

```python
"""Kimi provider — Moonshot AI (月之暗面) chat completions with tool calling."""

from bot.provider.openai_compat import OpenAICompatProvider


class KimiProvider(OpenAICompatProvider):
    ENV_KEY = "KIMI_API_KEY"

    def __init__(self, model: str):
        super().__init__(model)
        from bot.config import get_config
        self.API_URL = get_config().llm.kimi.api_url
```

- [ ] **Step 4: Register `KimiProvider` in the provider registry**

Modify `bot/provider/__init__.py`. The full replacement content is:

```python
"""Provider registry and factory."""

from bot.provider.base import BaseProvider
from bot.provider.anthropic import AnthropicProvider
from bot.provider.codex import CodexProvider
from bot.provider.glm import GLMProvider
from bot.provider.minimax import MinimaxProvider
from bot.provider.kimi import KimiProvider

__all__ = [
    "BaseProvider",
    "AnthropicProvider",
    "CodexProvider",
    "GLMProvider",
    "MinimaxProvider",
    "KimiProvider",
    "get_provider",
    "get_default_provider",
]

_PROVIDERS: dict[str, type[BaseProvider]] = {
    "anthropic": AnthropicProvider,
    "codex": CodexProvider,
    "glm": GLMProvider,
    "minimax": MinimaxProvider,
    "kimi": KimiProvider,
}


def get_provider(provider_id: str, model: str) -> BaseProvider:
    """Get a Provider instance by provider_id and model."""
    cls = _PROVIDERS.get(provider_id)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_id}")
    return cls(model=model)


def get_default_provider() -> BaseProvider:
    """Get the default provider based on config."""
    from bot.config import get_config
    cfg = get_config()
    provider = cfg.llm.provider
    if provider == "codex":
        return get_provider("codex", cfg.llm.codex.model)
    if provider == "glm":
        return get_provider("glm", cfg.llm.glm.model)
    if provider == "minimax":
        return get_provider("minimax", cfg.llm.minimax.model)
    if provider == "kimi":
        return get_provider("kimi", cfg.llm.kimi.model)
    return get_provider("anthropic", cfg.llm.anthropic.model)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/provider/test_registry.py::TestProviderRegistry::test_get_kimi_provider -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/provider/kimi.py bot/provider/__init__.py tests/provider/test_registry.py
git commit -m "feat(provider): add Kimi (Moonshot AI) as an LLM provider"
```

---

## Task 3: Cover `get_default_provider()` kimi branch

**Files:**
- Test: `tests/provider/test_registry.py` (add new test)

- [ ] **Step 1: Write the test**

Add this method to `class TestProviderRegistry:` in `tests/provider/test_registry.py`, right after `test_get_default_provider_codex`:

```python
    def test_get_default_provider_kimi(self, monkeypatch):
        from bot.config import reset_config
        from bot.config_schema import AppConfig
        from bot.provider.kimi import KimiProvider
        import bot.config as cfg_mod
        kimi_cfg = AppConfig.from_dict({"llm": {"provider": "kimi", "kimi": {"model": "kimi-latest"}}})
        monkeypatch.setattr(cfg_mod, "_config", kimi_cfg)
        try:
            provider = get_default_provider()
            assert isinstance(provider, KimiProvider)
            assert provider.model == "kimi-latest"
        finally:
            reset_config()
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/provider/test_registry.py::TestProviderRegistry::test_get_default_provider_kimi -v`
Expected: PASS (the `kimi` branch was already added in Task 2 Step 4).

- [ ] **Step 3: Run the full registry file to confirm no regressions**

Run: `uv run pytest tests/provider/test_registry.py -v`
Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/provider/test_registry.py
git commit -m "test(provider): cover get_default_provider kimi branch"
```

---

## Task 4: Add Kimi entries to `config.yaml` and `.env.example`

**Files:**
- Modify: `config.yaml:1-17`
- Modify: `.env.example`

- [ ] **Step 1: Add `kimi` section under `llm:` in `config.yaml`**

Insert the `kimi:` block right after the existing `minimax:` block (around line 13-14). After the edit, the top of `config.yaml` should look like:

```yaml
llm:
  provider: minimax
  anthropic:
    model: claude-sonnet-4-20250514
    api_url: https://api.anthropic.com/v1/messages
  codex:
    model: gpt-5.3-codex
    api_url: https://chatgpt.com/backend-api/codex/responses
  glm:
    model: glm-4.7-flash
    api_url: https://api.z.ai/api/paas/v4/chat/completions
  minimax:
    model: MiniMax-M2.7
    api_url: https://api.minimaxi.com/v1/text/chatcompletion_v2
  kimi:
    model: kimi-latest
    api_url: https://api.moonshot.cn/v1/chat/completions
  max_history: 25
  max_tokens: 4096
  tools_enabled: true
```

Do NOT change `provider: minimax`.

- [ ] **Step 2: Add `KIMI_API_KEY` to `.env.example`**

Open `.env.example`. Find the block:

```
# Optional — MiniMax API key
# MINIMAX_API_KEY=xxx
```

Immediately after that block (before the `# Browser backend selection` block), add:

```
# Optional — Kimi (Moonshot AI, 月之暗面) API key
# KIMI_API_KEY=xxx
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

Run: `uv run pytest`
Expected: all tests PASS (coverage threshold ≥60% still met).

- [ ] **Step 4: Commit**

```bash
git add config.yaml .env.example
git commit -m "feat(config): document Kimi provider in config.yaml and .env.example"
```

---

## Final Verification

- [ ] **Step 1: Smoke-check the import graph**

Run: `uv run python -c "from bot.provider import KimiProvider, get_provider; p = get_provider('kimi', 'kimi-latest'); print(type(p).__name__, p.model, p.API_URL)"`

Expected stdout:
```
KimiProvider kimi-latest https://api.moonshot.cn/v1/chat/completions
```

- [ ] **Step 2: Confirm the full suite is green**

Run: `uv run pytest --cov=bot --cov-report=term-missing | tail -30`
Expected: all tests pass, coverage ≥60%.

- [ ] **Step 3: Verify clean git state**

Run: `git status && git log --oneline -5`
Expected: working tree clean; four new commits on top of the base:
1. `feat(config): add KimiConfig dataclass to LLMConfig`
2. `feat(provider): add Kimi (Moonshot AI) as an LLM provider`
3. `test(provider): cover get_default_provider kimi branch`
4. `feat(config): document Kimi provider in config.yaml and .env.example`

---

## Notes for the implementer

- **Do not** switch the default `llm.provider` — it must remain `minimax`. User explicitly asked for Kimi as an option, not a default swap.
- **Do not** add a dedicated `tests/provider/test_kimi.py`. GLM has no equivalent and the shared `openai_compat` wire layer is covered by `test_transform.py` and the existing provider tests. Registry-level tests are sufficient.
- **API key in env:** at runtime users must set `KIMI_API_KEY` in `.env`. Tests don't need it — `KimiProvider.__init__` only reads config, not the key. The key is read lazily in `_get_api_key()` when a real request is made.
- **No body quirks:** Kimi uses standard `max_tokens`. Do NOT copy MiniMax's `_build_body` override.
