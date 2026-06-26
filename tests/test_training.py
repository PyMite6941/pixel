from training.collector import TrainingCollector, TrainingExample
from training.export import export_jsonl, export_json, export_csv


class TestTrainingCollector:
    def setup_method(self):
        self.collector = TrainingCollector()
        self.collector.clear()

    def test_record_creates_example(self):
        ex = self.collector.record(
            prompt="hello",
            domain="general",
            provider="groq",
            final_response="hi there",
            quality_score=50,
            successful=True,
        )
        assert ex.prompt == "hello"
        assert ex.domain == "general"
        assert ex.provider == "groq"
        assert ex.quality_score == 50
        assert ex.successful == True

    def test_record_with_tool(self):
        ex = self.collector.record(
            prompt="search for python",
            domain="coding",
            provider="groq",
            final_response="found results",
            quality_score=80,
            successful=True,
            tool_name="search",
            tool_result="some results",
        )
        assert ex.tool_name == "search"
        assert ex.tool_result == "some results"

    def test_get_stats_empty(self):
        self.collector.clear()
        stats = self.collector.get_stats()
        assert stats["total_examples"] == 0
        assert stats["success_rate"] == 0

    def test_get_stats_with_data(self):
        self.collector.clear()
        self.collector.record("a", "coding", "groq", "resp", 80, True)
        self.collector.record("b", "math", "gemini", "resp", 90, True)
        self.collector.record("c", "coding", "groq", "resp", 20, False)

        stats = self.collector.get_stats()
        assert stats["total_examples"] == 3
        assert stats["successful"] == 2
        assert stats["success_rate"] == 66.7
        assert stats["by_domain"]["coding"] == 2
        assert stats["by_domain"]["math"] == 1
        assert stats["by_provider"]["groq"] == 2

    def test_get_recent(self):
        self.collector.clear()
        for i in range(5):
            self.collector.record(f"q{i}", "general", "groq", f"a{i}", 50, True)
        recent = self.collector.get_recent(3)
        assert len(recent) == 3


class TestTrainingExport:
    def setup_method(self):
        self.collector = TrainingCollector()
        self.collector.clear()
        self.collector.record("test prompt", "coding", "groq", "test response", 75, True, tool_name="shell")

    def test_export_jsonl(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            from pathlib import Path
            result = export_jsonl(self.collector, Path(path))
            content = Path(path).read_text()
            assert "test prompt" in content
            assert "coding" in content
        finally:
            Path(path).unlink(missing_ok=True)

    def test_export_json(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            from pathlib import Path
            result = export_json(self.collector, Path(path))
            import json
            data = json.loads(Path(path).read_text())
            assert len(data) == 1
            assert data[0]["prompt"] == "test prompt"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_export_csv(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            path = f.name
        try:
            from pathlib import Path
            result = export_csv(self.collector, Path(path))
            content = Path(path).read_text()
            assert "prompt" in content
            assert "test prompt" in content
        finally:
            Path(path).unlink(missing_ok=True)
