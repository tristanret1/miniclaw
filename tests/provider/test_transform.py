"""Tests for bot.provider.transform — message sanitization logic."""

from bot.provider.transform import sanitize, sanitize_for_anthropic


class TestSanitizeForAnthropic:
    def test_empty_messages(self):
        assert sanitize_for_anthropic([]) == []

    def test_simple_alternation(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "bye"},
        ]
        result = sanitize_for_anthropic(msgs)
        assert len(result) == 3
        assert [m["role"] for m in result] == ["user", "assistant", "user"]

    def test_starts_with_assistant_dropped(self):
        msgs = [
            {"role": "assistant", "content": "oops"},
            {"role": "user", "content": "hi"},
        ]
        result = sanitize_for_anthropic(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_tool_use_with_matching_result_preserved(self):
        msgs = [
            {"role": "user", "content": "run ls"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "ok"},
                {"type": "tool_use", "id": "t1", "name": "exec", "input": {"command": "ls"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "file.txt"},
            ]},
            {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
        ]
        result = sanitize_for_anthropic(msgs)
        assert len(result) == 4

    def test_tool_use_without_result_dropped(self):
        msgs = [
            {"role": "user", "content": "run ls"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "exec", "input": {}},
            ]},
            # No tool_result follows — just a new user message
            {"role": "user", "content": "next question"},
        ]
        result = sanitize_for_anthropic(msgs)
        # tool_use pair dropped, only "run ls" and "next question" survive (but consecutive user → deduped)
        assert all(m["role"] != "assistant" or not any(
            b.get("type") == "tool_use" for b in (m.get("content") if isinstance(m.get("content"), list) else [])
        ) for m in result)

    def test_tool_use_with_mismatched_result_dropped(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "exec", "input": {}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "wrong_id", "content": "x"},
            ]},
        ]
        result = sanitize_for_anthropic(msgs)
        # Mismatched pair dropped
        assert not any(
            isinstance(m.get("content"), list) and any(
                b.get("type") == "tool_use" for b in m["content"]
            )
            for m in result
        )

    def test_orphan_tool_result_without_preceding_use_dropped(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "orphan"},
            ]},
            {"role": "assistant", "content": "hi"},
        ]
        result = sanitize_for_anthropic(msgs)
        # Orphan tool_result dropped, but assistant also dropped (can't start with assistant)
        # Actually assistant remains if user is dropped... let's check
        # After dropping orphan tool_result at index 0, assistant at index 1 is first
        # Then "starts with user" check removes it
        assert len(result) == 0

    def test_consecutive_same_role_deduped(self):
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "reply"},
        ]
        result = sanitize_for_anthropic(msgs)
        assert len(result) == 2
        assert result[0]["content"] == "first"
        assert result[1]["content"] == "reply"

    def test_multiple_tool_uses_with_matching_results(self):
        msgs = [
            {"role": "user", "content": "do both"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "exec", "input": {}},
                {"type": "tool_use", "id": "t2", "name": "memory_save", "input": {}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
                {"type": "tool_result", "tool_use_id": "t2", "content": "saved"},
            ]},
        ]
        result = sanitize_for_anthropic(msgs)
        assert len(result) == 3

    def test_tool_pair_followed_by_normal_messages(self):
        msgs = [
            {"role": "user", "content": "run"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "exec", "input": {}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "done"},
            ]},
            {"role": "assistant", "content": "result"},
            {"role": "user", "content": "thanks"},
        ]
        result = sanitize_for_anthropic(msgs)
        assert len(result) == 5

    def test_complex_multi_turn_with_tools(self):
        """Realistic scenario: normal chat → tool → normal chat."""
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
            {"role": "user", "content": "list files"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "sure"},
                {"type": "tool_use", "id": "t1", "name": "exec", "input": {"command": "ls"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "file.py"},
            ]},
            {"role": "assistant", "content": [{"type": "text", "text": "found file.py"}]},
            {"role": "user", "content": "great"},
            {"role": "assistant", "content": "anything else?"},
        ]
        result = sanitize_for_anthropic(msgs)
        assert len(result) == 8
        assert [m["role"] for m in result] == [
            "user", "assistant", "user", "assistant",
            "user", "assistant", "user", "assistant",
        ]


class TestSanitizeRouter:
    def test_routes_to_anthropic(self):
        msgs = [
            {"role": "assistant", "content": "should be dropped"},
            {"role": "user", "content": "hi"},
        ]
        result = sanitize(msgs, "anthropic")
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_unknown_provider_passthrough(self):
        msgs = [
            {"role": "assistant", "content": "not dropped"},
            {"role": "user", "content": "hi"},
        ]
        result = sanitize(msgs, "unknown_provider")
        assert len(result) == 2
