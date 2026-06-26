from skills.registry import SkillRegistry


class TestSkillRegistry:
    def setup_method(self):
        self.registry = SkillRegistry()

    def test_discovers_skills(self):
        assert len(self.registry.skill_names) > 0

    def test_has_think_skill(self):
        assert "think" in self.registry.skill_names

    def test_has_shell_skill(self):
        assert "shell" in self.registry.skill_names

    def test_has_web_fetch_skill(self):
        assert "web_fetch" in self.registry.skill_names

    def test_has_file_ops_skill(self):
        assert "file_ops" in self.registry.skill_names

    def test_get_returns_none_for_unknown(self):
        assert self.registry.get("nonexistent_skill") is None

    def test_get_returns_skill(self):
        skill = self.registry.get("think")
        assert skill is not None
        assert skill.name == "think"
        assert skill.description

    def test_skills_have_descriptions(self):
        for name, skill in self.registry.skills.items():
            assert skill.description, f"Skill '{name}' has no description"

    def test_run_unknown_returns_error_message(self):
        result = self.registry.run("nonexistent")
        assert "not found" in result

    def test_think_skill_executes(self):
        result = self.registry.run("think", task="hello")
        assert result is not None
        assert "Task" in result
