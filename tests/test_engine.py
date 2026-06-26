import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.registry import DynamicToolRegistry, ToolDef
from engine.engine import SmartEngine
from engine.composer import ToolComposer
from engine.planner import Planner, PlanStep


class TestToolDef:
    def test_basic_creation(self):
        t = ToolDef(name="test", description="A test", parameters={"q": "str"}, source="builtin")
        assert t.name == "test"
        assert t.description == "A test"
        assert t.parameters == {"q": "str"}
        assert t.source == "builtin"
        assert t.is_composite is False

    def test_generated_source(self):
        t = ToolDef(name="gen", description="Generated", source="generated", code="def gen(): pass")
        assert t.source == "generated"
        assert t.code == "def gen(): pass"


class TestDynamicToolRegistry:
    def test_discover_builtins(self):
        from skills.registry import SkillRegistry
        skills = SkillRegistry()
        reg = DynamicToolRegistry(skills)
        tools = reg.list_tools()
        assert len(tools) >= 10
        names = [t.name for t in tools]
        assert "search" in names
        assert "think" in names
        assert "web_fetch" in names

    def test_search_tools(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        hits = reg.search_tools("web_fetch")
        assert len(hits) >= 1
        assert hits[0].name == "web_fetch"

    def test_search_no_match(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        hits = reg.search_tools("xyznonexistent12345")
        assert hits == []

    def test_register_and_remove(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        t = ToolDef(name="custom_test", description="Custom", source="generated", code="x=1")
        reg.register_tool(t)
        assert reg.get_tool("custom_test") is not None
        assert reg.remove_tool("custom_test") is True
        assert reg.get_tool("custom_test") is None

    def test_tool_count_by_source(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        t = ToolDef(name="custom_test", description="Custom", source="generated")
        reg.register_tool(t)
        counts = reg.tool_count_by_source()
        assert counts.get("builtin", 0) >= 10
        assert counts.get("generated", 0) >= 1

    def test_get_tool_descriptions(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        desc = reg.get_tool_descriptions()
        assert "search" in desc
        assert "think" in desc

    def test_get_tool_nonexistent(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        assert reg.get_tool("does_not_exist") is None

    def test_generated_dir_created(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        assert reg._generated_dir.exists()


class TestPlanner:
    def test_plan_search_task(self):
        planner = Planner()
        steps = planner.plan("search the web for AI news", [])
        tools = [s.tool for s in steps]
        assert "search" in tools

    def test_plan_coding_task(self):
        planner = Planner()
        steps = planner.plan("write python code to sort a list", [])
        tools = [s.tool for s in steps]
        assert "run_code" in tools

    def test_plan_shell_task(self):
        planner = Planner()
        steps = planner.plan("run a command to list files", [])
        tools = [s.tool for s in steps]
        assert "shell" in tools

    def test_plan_generic_task(self):
        planner = Planner()
        steps = planner.plan("what is the meaning of life", [])
        assert len(steps) >= 1

    def test_plan_always_ends_with_synthesize(self):
        planner = Planner()
        steps = planner.plan("hello", [])
        assert steps[-1].action == "synthesize"

    def test_plan_file_task(self):
        planner = Planner()
        steps = planner.plan("read the file and save results", [])
        tools = [s.tool for s in steps]
        assert "file_ops" in tools

    def test_plan_web_task(self):
        planner = Planner()
        steps = planner.plan("fetch https://example.com", [])
        tools = [s.tool for s in steps]
        assert "web_fetch" in tools

    def test_plan_dependencies(self):
        planner = Planner()
        steps = planner.plan("search for news and fetch a website", [])
        deps = [s.depends_on for s in steps if s.depends_on]
        assert len(deps) > 0


class TestToolComposer:
    def test_compose_two_tools(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        composer = ToolComposer(reg)
        tool = composer.compose("search_fetch", "Search then fetch", ["search", "web_fetch"], {"query": "str"})
        assert tool.name == "search_fetch"
        assert tool.is_composite is True
        assert tool.source == "composed"

    def test_compose_invalid_tool(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        composer = ToolComposer(reg)
        try:
            composer.compose("bad", "bad", ["nonexistent_tool_xyz"])
            assert False, "Should have raised"
        except ValueError:
            pass

    def test_compose_merges_params(self):
        from skills.registry import SkillRegistry
        reg = DynamicToolRegistry(SkillRegistry())
        composer = ToolComposer(reg)
        t = reg.get_tool("search")
        t2 = reg.get_tool("think")
        if t and t2:
            tool = composer.compose("s_t", "test", ["search", "think"])
            assert tool.parameters is not None


class TestSmartEngineInit:
    def test_engine_initializes(self):
        class FakePixel:
            class Skills:
                def __init__(self):
                    self._skills = {}
                @property
                def skills(self):
                    return self._skills
                @property
                def skill_names(self):
                    return []
                def get(self, name):
                    return None
                def run(self, name, **kw):
                    return None
            def __init__(self):
                self.skills = self.Skills()
            def ask(self, prompt):
                return "mock reply"
        engine = SmartEngine(pixel_instance=FakePixel())
        assert engine.registry is not None
        assert engine.planner is not None
        assert engine.composer is not None
        assert engine.generator is not None
        assert engine.trainer is not None

    def test_engine_stats(self):
        class FakePixel:
            class Skills:
                @property
                def skills(self): return {}
                @property
                def skill_names(self): return []
                def get(self, n): return None
                def run(self, n, **kw): return None
            def __init__(self):
                self.skills = self.Skills()
            def ask(self, prompt): return "mock"
        engine = SmartEngine(pixel_instance=FakePixel())
        stats = engine.get_stats()
        assert "total_tools" in stats
        assert "executions" in stats

    def test_engine_find_tools_no_training(self):
        class FakePixel:
            class Skills:
                @property
                def skills(self): return {}
                @property
                def skill_names(self): return []
                def get(self, n): return None
                def run(self, n, **kw): return None
            def __init__(self):
                self.skills = self.Skills()
            def ask(self, prompt): return "mock"
        engine = SmartEngine(pixel_instance=FakePixel())
        tools = engine.find_tools_for("test")
        assert isinstance(tools, list)
