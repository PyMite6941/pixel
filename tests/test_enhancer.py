from self.enhancer import SelfEnhancer


class TestSelfEnhancer:
    def setup_method(self):
        self.enhancer = SelfEnhancer()

    def test_analyze_benchmark_empty(self):
        analysis = self.enhancer.analyze_benchmark({
            "timestamp": "2024-01-01",
            "by_provider": {},
            "by_domain": {},
            "results": [],
        })
        assert "weak_domains" in analysis
        assert "provider_gaps" in analysis
        assert "recommendations" in analysis
        assert analysis["overall_health"] in ("good", "needs_improvement")

    def test_analyze_benchmark_identifies_weak_domains(self):
        analysis = self.enhancer.analyze_benchmark({
            "timestamp": "2024-01-01",
            "by_provider": {"groq": {"avg_quality": 80, "avg_time_ms": 300, "total_cost": 0, "errors": 0, "runs": [{}]}},
            "by_domain": {
                "coding": {"avg_quality": 85, "total_cost": 0, "quality_scores": [85]},
                "math": {"avg_quality": 30, "total_cost": 0, "quality_scores": [30]},
            },
            "results": [],
        })
        assert len(analysis["weak_domains"]) > 0
        weak_names = [w["domain"] for w in analysis["weak_domains"]]
        assert "math" in weak_names
        assert analysis["overall_health"] == "needs_improvement"

    def test_generate_improvement_plan_without_data(self):
        plan = self.enhancer.generate_improvement_plan(run_data=None)
        assert plan["status"] == "no_data"

    def test_generate_improvement_plan_with_data(self):
        plan = self.enhancer.generate_improvement_plan({
            "timestamp": "2024-01-01",
            "by_provider": {},
            "by_domain": {
                "coding": {"avg_quality": 90, "total_cost": 0, "quality_scores": [90]},
            },
            "results": [{"provider": "groq", "domain": "coding", "quality_score": 90}],
            "total_prompts": 1,
            "total_cost": 0,
            "avg_quality_score": 90,
            "avg_response_time_ms": 100,
        })
        assert "immediate_actions" in plan
        assert "short_term_actions" in plan
        assert "long_term_actions" in plan

    def test_list_analyses_empty(self):
        analyses = self.enhancer.list_analyses()
        assert isinstance(analyses, list)

    def test_list_plans_empty(self):
        plans = self.enhancer.list_plans()
        assert isinstance(plans, list)

    def test_analyze_highlights_single_provider_gap(self):
        analysis = self.enhancer.analyze_benchmark({
            "timestamp": "2024-01-01",
            "by_provider": {"groq": {"avg_quality": 75, "avg_time_ms": 300, "total_cost": 0, "errors": 0, "runs": [{}]}},
            "by_domain": {"general": {"avg_quality": 75, "total_cost": 0, "quality_scores": [75]}},
            "results": [],
        })
        gaps = analysis["provider_gaps"]
        has_single = any(g["gap"] == "single_provider" for g in gaps)
        assert has_single
