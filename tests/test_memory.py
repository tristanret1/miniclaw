"""Tests for bot.memory — save, search, BM25, vector helpers."""

import bot.memory as memory_mod
from bot.memory import (
    _cosine_similarity,
    _merge_scores,
    _pack_vector,
    _unpack_vector,
    save,
    search,
    should_flush,
    get_flush_prompt,
)


class TestSaveAndSearch:
    async def test_save_and_search_bm25(self, memory_db):
        await save("The user prefers dark mode", tags=["preference"])
        result = await search("dark mode")
        assert "dark mode" in result
        assert "#" in result  # contains memory ID

    async def test_save_with_tags(self, memory_db):
        await save("Important fact", tags=["fact", "important"])
        result = await search("important")
        assert "fact" in result

    async def test_search_no_results(self, memory_db):
        result = await search("nonexistent_query_xyz")
        assert "No matches" in result

    async def test_multiple_saves_ranked(self, memory_db):
        await save("Python is a programming language")
        await save("Python snake is a reptile")
        await save("I love programming in Python every day")
        result = await search("Python programming")
        # Should find results
        assert "Python" in result

    async def test_daily_log_created(self, memory_db):
        _, mem_dir = memory_db
        await save("test log entry")
        md_files = list(mem_dir.glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text()
        assert "test log entry" in content

    async def test_daily_log_appends(self, memory_db):
        _, mem_dir = memory_db
        await save("first entry")
        await save("second entry")
        md_files = list(mem_dir.glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text()
        assert "first entry" in content
        assert "second entry" in content

    async def test_fts5_special_chars_fallback(self, memory_db):
        """FTS5 special chars (AND/OR/NOT) should not crash."""
        await save("some content here")
        # These should not raise, even if FTS5 interprets them specially
        result = await search("AND OR NOT")
        # May or may not find results, but should not crash
        assert isinstance(result, str)


class TestVectorHelpers:
    def test_pack_unpack_roundtrip(self):
        vec = [0.1, 0.2, 0.3, -0.5, 1.0]
        packed = _pack_vector(vec)
        unpacked = _unpack_vector(packed)
        assert len(unpacked) == len(vec)
        for a, b in zip(vec, unpacked):
            assert abs(a - b) < 1e-6

    def test_cosine_similarity_identical(self):
        vec = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_cosine_similarity_opposite(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_cosine_similarity_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 1.0]
        assert _cosine_similarity(a, b) == 0.0


class TestMergeScores:
    def test_merge_basic(self):
        bm25 = {1: 1.0, 2: 0.5}
        vector = {2: 1.0, 3: 0.8}
        result = _merge_scores(bm25, vector, max_results=3)
        ids = [mid for mid, _ in result]
        assert 1 in ids
        assert 2 in ids
        assert 3 in ids

    def test_merge_respects_max_results(self):
        bm25 = {i: 1.0 / (i + 1) for i in range(10)}
        vector = {}
        result = _merge_scores(bm25, vector, max_results=3)
        assert len(result) == 3

    def test_merge_weighted_correctly(self):
        bm25 = {1: 1.0}
        vector = {1: 1.0}
        result = _merge_scores(bm25, vector, max_results=1)
        mid, score = result[0]
        assert mid == 1
        # BM25_WEIGHT=0.4, VECTOR_WEIGHT=0.6 → 0.4 + 0.6 = 1.0
        assert abs(score - 1.0) < 1e-6


class TestFlush:
    def test_should_flush_below_threshold(self):
        history = [{"role": "user", "content": "short"}]
        assert should_flush(history) is False

    def test_should_flush_above_threshold(self):
        # Create history exceeding 80k chars
        big_msg = "x" * 90_000
        history = [{"role": "user", "content": big_msg}]
        assert should_flush(history) is True

    def test_get_flush_prompt_nonempty(self):
        prompt = get_flush_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "memory" in prompt.lower()
