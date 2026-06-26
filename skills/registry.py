from pathlib import Path
from typing import Any

from skills.base_skill import BaseSkill

_ROOT = Path(__file__).parent


def _discover() -> dict[str, BaseSkill]:
    skills: dict[str, BaseSkill] = {}
    for f in sorted(_ROOT.glob("*.py")):
        if f.stem in ("__init__", "base_skill", "registry"):
            continue
        module_name = f"skills.{f.stem}"
        try:
            import importlib
            mod = importlib.import_module(module_name)
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseSkill) and attr is not BaseSkill:
                    instance = attr()
                    skills[instance.name] = instance
        except Exception as e:
            pass
    return skills


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, BaseSkill] = _discover()

    @property
    def skills(self) -> dict[str, BaseSkill]:
        return dict(self._skills)

    @property
    def skill_names(self) -> list[str]:
        return sorted(self._skills.keys())

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def run(self, name: str, **params: Any) -> Any:
        skill = self.get(name)
        if skill is None:
            return f"Skill '{name}' not found. Available: {', '.join(self.skill_names)}"
        try:
            return skill.execute(**params)
        except Exception as e:
            return f"Skill '{name}' failed: {e}"

    def describe_all(self) -> str:
        lines = []
        for name in self.skill_names:
            skill = self._skills[name]
            lines.append(f"  {name}: {skill.description}")
        return "\n".join(lines)
