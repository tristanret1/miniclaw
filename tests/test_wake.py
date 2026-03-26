"""Tests for bot.wake — wake word detection from STT text."""

import pytest


class TestWakeWordCheck:
    """Wake word matching tests."""

    def test_detects_wake_word_at_start(self):
        from bot.wake import check
        result = check("miniclaw what time is it", wake_words=["miniclaw"])
        assert result == "what time is it"

    def test_detects_wake_word_case_insensitive(self):
        from bot.wake import check
        result = check("MiniClaw tell me a joke", wake_words=["miniclaw"])
        assert result == "tell me a joke"

    def test_detects_chinese_wake_word(self):
        from bot.wake import check
        result = check("小爪 今天天气怎么样", wake_words=["小爪"])
        assert result == "今天天气怎么样"

    def test_returns_none_without_wake_word(self):
        from bot.wake import check
        result = check("what time is it", wake_words=["miniclaw"])
        assert result is None

    def test_empty_text_returns_none(self):
        from bot.wake import check
        result = check("", wake_words=["miniclaw"])
        assert result is None

    def test_wake_word_only_returns_empty_command(self):
        from bot.wake import check
        result = check("miniclaw", wake_words=["miniclaw"])
        assert result == ""

    def test_multiple_wake_words(self):
        from bot.wake import check
        result = check("小爪 你好", wake_words=["miniclaw", "小爪"])
        assert result == "你好"

    def test_wake_word_with_punctuation(self):
        """Handle STT adding comma after wake word: 'miniclaw, do X'."""
        from bot.wake import check
        result = check("miniclaw, play some music", wake_words=["miniclaw"])
        assert result == "play some music"

    def test_wake_word_mid_sentence_ignored(self):
        """Only match wake word at the start of the utterance."""
        from bot.wake import check
        result = check("hey miniclaw do something", wake_words=["miniclaw"])
        assert result is None
