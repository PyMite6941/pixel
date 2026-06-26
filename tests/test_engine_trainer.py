import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.trainer import EngineTrainer
from engine.registry import DynamicToolRegistry


class TestEngineTrainer:
    def test_train_on_all_tools(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        trainer = EngineTrainer(reg)
        result = trainer.train_on_all_tools()
        assert result["trained"] >= 10
        assert result["errors"] == 0

    def test_basic_analysis(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        trainer = EngineTrainer(reg)
        tool = reg.get_tool("search")
        assert tool is not None
        analysis = trainer._basic_analysis(tool)
        assert "summary" in analysis
        assert "capabilities" in analysis
        assert "use_cases" in analysis
        assert "keywords" in analysis

    def test_find_best_tools_keyword(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        trainer = EngineTrainer(reg)
        trainer.train_on_all_tools()
        hits = trainer.find_best_tools("search the web for AI news", top_k=3)
        assert len(hits) > 0
        tool_names = [h["tool"] for h in hits]
        assert "search" in tool_names

    def test_find_best_tools_coding(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        trainer = EngineTrainer(reg)
        trainer.train_on_all_tools()
        hits = trainer.find_best_tools("write a python script to parse JSON", top_k=3)
        tool_names = [h["tool"] for h in hits]
        assert "run_code" in tool_names or "file_ops" in tool_names

    def test_categorize_task(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        trainer = EngineTrainer(reg)
        assert trainer._categorize_task("write code") == "coding"
        assert trainer._categorize_task("search for x") == "research"
        assert trainer._categorize_task("read file") == "file_management"
        assert trainer._categorize_task("analyze data") == "analysis"
        assert trainer._categorize_task("run command") == "execution"
        assert trainer._categorize_task("hello world") == "general"

    def test_learn_from_execution(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        trainer = EngineTrainer(reg)
        trainer.learn_from_execution("test task", [
            {"tool": "search", "action": "search", "status": "done"},
            {"tool": "think", "action": "think", "status": "done"},
        ], success=True, duration=2.5)
        assert trainer.get_training_status()["execution_patterns"] >= 1

    def test_suggest_tool_chains_no_patterns(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        trainer = EngineTrainer(reg)
        chain = trainer.suggest_tool_chains("search for something")
        assert chain == []

    def test_suggest_tool_chains_with_patterns(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        trainer = EngineTrainer(reg)
        trainer.learn_from_execution("write code in python", [
            {"tool": "run_code", "action": "code", "status": "done"},
            {"tool": "file_ops", "action": "file", "status": "done"},
        ], success=True, duration=1.0)
        chain = trainer.suggest_tool_chains("write python code")
        assert "run_code" in chain or chain == []

    def test_generate_tool_catalog(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        trainer = EngineTrainer(reg)
        trainer.train_on_all_tools()
        catalog = trainer.generate_tool_catalog()
        assert "SMART ENGINE" in catalog
        assert "search" in catalog.lower()
        assert "think" in catalog.lower()

    def test_get_training_status(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        trainer = EngineTrainer(reg)
        status = trainer.get_training_status()
        assert "tools_trained" in status
        assert "execution_patterns" in status
        assert "total_tools" in status

    def test_tool_relationships(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        trainer = EngineTrainer(reg)
        trainer.train_on_all_tools()
        for name, knowledge in trainer._knowledge.items():
            if knowledge.get("related_tools"):
                assert len(knowledge["related_tools"]) > 0
                break
