from evals.harness import EvalHarness, _score_response_quality
from evals.datasets import get_domain_prompts, get_all_prompts, get_domain_names, DOMAIN_PROMPTS
from evals.reporter import (
    generate_markdown_report, generate_html_report,
    generate_json_report, generate_csv_report,
    save_report, list_reports,
)


class TestEvalDatasets:
    def test_get_domain_prompts_returns_list(self):
        prompts = get_domain_prompts("coding")
        assert len(prompts) > 0
        assert all(isinstance(p, tuple) and len(p) == 2 for p in prompts)

    def test_get_domain_prompts_unknown_falls_back(self):
        prompts = get_domain_prompts("nonexistent")
        assert len(prompts) > 0

    def test_get_all_prompts_returns_all(self):
        all_p = get_all_prompts()
        domain_counts = sum(len(v) for v in DOMAIN_PROMPTS.values())
        assert len(all_p) == domain_counts

    def test_get_domain_names(self):
        names = get_domain_names()
        assert "coding" in names
        assert "math" in names
        assert "writing" in names


class TestQualityScoring:
    def test_empty_response_scores_zero(self):
        result = _score_response_quality("hello", "", "general")
        assert result["score"] == 0

    def test_good_response_scores_high(self):
        result = _score_response_quality(
            "write a python function",
            "Here is a Python function:\n\n```python\ndef hello():\n    print('hello')\n```\n\nThis function prints hello.",
            "coding",
        )
        assert result["score"] >= 40
        assert result["has_code"] == True

    def test_structured_response_scores_well(self):
        result = _score_response_quality(
            "explain something",
            "Here are the key points:\n1. First point\n2. Second point\n3. Third point\n\nIn summary, this is important.",
            "general",
        )
        assert result["score"] >= 30
        assert result["has_structure"] == True


class TestEvalHarness:
    def test_estimate_tokens(self):
        harness = EvalHarness()
        assert harness.estimate_tokens("") == 1
        assert harness.estimate_tokens("hello") == 1
        assert harness.estimate_tokens("x" * 100) == 25

    def test_list_runs_empty_initially(self):
        harness = EvalHarness()
        runs = harness.list_runs()
        assert isinstance(runs, list)

    def test_compile_run_empty(self):
        harness = EvalHarness()
        run = harness._compile_run(["groq"])
        assert run.total_prompts == 0
        assert run.avg_quality_score == 0


class TestReporter:
    def test_markdown_report_contains_header(self):
        report = generate_markdown_report({
            "timestamp": "2024-01-01",
            "total_prompts": 10,
            "avg_quality_score": 75.5,
            "avg_response_time_ms": 500,
            "total_cost": 0.01,
            "by_provider": {},
            "by_domain": {},
        })
        assert "Pixel AI Benchmark Report" in report
        assert "75.5" in report

    def test_html_report_contains_header(self):
        report = generate_html_report({
            "timestamp": "2024-01-01",
            "total_prompts": 10,
            "avg_quality_score": 80,
            "avg_response_time_ms": 300,
            "total_cost": 0.02,
            "by_provider": {},
            "by_domain": {},
        })
        assert "Pixel AI Benchmark Report" in report
        assert "80" in report

    def test_json_report_contains_data(self):
        report = generate_json_report({
            "timestamp": "2024-01-01",
            "total_prompts": 5,
            "avg_quality_score": 70,
            "avg_response_time_ms": 400,
            "total_cost": 0.005,
            "by_provider": {},
            "by_domain": {},
            "results": [],
        })
        assert '"total_prompts": 5' in report

    def test_csv_report_contains_headers(self):
        report = generate_csv_report({
            "results": [
                {"provider": "groq", "domain": "coding", "quality_score": 80, "response_time_ms": 300, "cost": 0.001, "input_tokens": 50, "output_tokens": 100, "error": ""},
            ]
        })
        assert "Provider,Domain,Quality" in report
        assert "groq,coding,80" in report
