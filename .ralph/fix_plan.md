# Ralph Fix Plan
## Completed
- [x] Restore test coverage to ≥60% threshold (was 57.96%, now 60.31%)
  - Added Codex sanitizer + strip_tool_blocks tests (transform.py: 52% → 100%)
  - Added session_keys + discord utils tests (100% coverage)
  - Added _get_embedding tests (memory.py: 61% → higher)
  - Added Agent dataclass tests (agent.py: 26% → higher)
  - Added LLM provider caching + agent resolve tests (llm.py: 83% → 100%)

- [x] Fix failing smoke test + restore 60% coverage threshold
  - Made AVFoundation/AVFAudio/Foundation imports lazy in audio_engine.py (consistent with stt.py/tts.py pattern)
  - Added test for Codex tool_result with list content (covers codex.py line 53)
  - Added test for non-zero exit with output in exec tool (covers exec.py line 83)
  - Added test for GITHUB_TOKEN env injection in exec tool (covers exec.py lines 55-56)
  - Added BaseProvider.close() tests (covers base.py lines 31-33)

## Notes
