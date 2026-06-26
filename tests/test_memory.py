import json
import tempfile
from pathlib import Path

from memory.token_tracker import estimate_tokens, record, summary
from memory.context_manager import context_size, needs_summary, compress


class TestTokenTracker:
    def test_estimate_tokens_empty(self):
        assert estimate_tokens("") == 1

    def test_estimate_tokens_short(self):
        assert estimate_tokens("hello") == 1

    def test_estimate_tokens_long(self):
        n = estimate_tokens("hello world foo bar")
        assert n > 0

    def test_estimate_four_chars_per_token(self):
        text = "x" * 100
        assert estimate_tokens(text) == 25

    def test_record_and_summary(self):
        record("test_provider", 100, 50)
        s = summary()
        assert s["input_tokens"] >= 100
        assert s["output_tokens"] >= 50


class TestContextManager:
    def test_context_size_empty(self):
        assert context_size([]) == 0

    def test_context_size_with_messages(self):
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        size = context_size(history)
        assert size > 0

    def test_needs_summary_false_for_small(self):
        history = [{"role": "user", "content": "hello"}]
        assert not needs_summary(history, max_tokens=1000)

    def test_compress_returns_same_for_small(self):
        history = [{"role": "user", "content": "hi"}]
        result = compress(history, max_tokens=1000)
        assert result == history
