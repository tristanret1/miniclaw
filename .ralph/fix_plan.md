# Ralph Fix Plan

## Completed
- [x] Project enabled for Ralph
- [x] Fix misleading CODEX_API_ENDPOINT import in provider/codex.py (import from bot.constants instead of re-export through bot.oauth.codex)
- [x] Run full test suite — fixed 16 failures + 12 errors by making openai/edge_tts imports lazy in stt.py and tts.py (335 pass, 4 skipped)
- [x] Enable `tools_enabled: true` in config.yaml

## High Priority
- [x] Verify Codex provider end-to-end (device auth flow + streaming) — Added 16 tests: SSE streaming (text, tool_use, mixed, errors, junk lines), call() (text, tool_use, malformed args), auth (refresh, expiry, no-creds). All 351 tests pass.

## Medium Priority
- [x] Add `__all__` exports to key modules (oauth/codex.py, oauth/anthropic.py, provider/__init__.py, tools/__init__.py) for cleaner API boundaries
- [x] Add integration smoke test that imports all bot modules without error — test_smoke.py verifies all submodules under bot/ import cleanly
- [ ] Review and commit unstaged config.yaml changes (voice enabled, wake word change)

## Low Priority
- [ ] Performance: session history loading could benefit from pagination for large histories
- [ ] Code cleanup: consolidate duplicate httpx client creation patterns across providers

## Notes
- Codebase is in good shape post-refactor (commit 46b17a3)
- 24 test files covering all major subsystems
- Coverage target: 60% (currently ~69%, 352 pass + 4 skipped)
- config.yaml has uncommitted local changes (voice enabled, wake word list trimmed)
