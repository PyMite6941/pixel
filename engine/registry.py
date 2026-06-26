import importlib
import inspect
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict[str, str] = field(default_factory=dict)
    code: Optional[str] = None
    auto_triggers: list[str] = field(default_factory=list)
    requires_subprocess: bool = False
    is_composite: bool = False
    source: str = "builtin"  # builtin, composed, generated


class DynamicToolRegistry:
    """Extends SkillRegistry with dynamic tool discovery, composition, and generation."""

    def __init__(self, skills_registry=None):
        self._tools: dict[str, ToolDef] = {}
        self._skill_registry = skills_registry
        self._discover_builtins()
        self._generated_dir = Path(__file__).parent / "generated"
        self._generated_dir.mkdir(exist_ok=True)

    def _discover_builtins(self):
        if self._skill_registry:
            for name, skill in self._skill_registry.skills.items():
                sig = inspect.signature(skill.execute)
                params = {}
                for p_name, p_param in sig.parameters.items():
                    if p_name not in ("kwargs", "params"):
                        params[p_name] = str(p_param.annotation) if p_param.annotation != inspect.Parameter.empty else "any"
                self._tools[name] = ToolDef(
                    name=name,
                    description=skill.description,
                    parameters=params,
                    auto_triggers=getattr(skill, "auto_triggers", []),
                    requires_subprocess=getattr(skill, "requires_subprocess", False),
                    source="builtin",
                )

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def search_tools(self, query: str) -> list[ToolDef]:
        q = query.lower()
        return [t for t in self._tools.values()
                if q in t.name.lower() or q in t.description.lower()]

    def get_tool(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    def register_tool(self, tool: ToolDef):
        self._tools[tool.name] = tool
        self._save_generated(tool)

    def remove_tool(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    def _save_generated(self, tool: ToolDef):
        if tool.source in ("composed", "generated") and tool.code:
            filepath = self._generated_dir / f"{tool.name}.py"
            filepath.write_text(tool.code)

    def generate_code(self, tool: ToolDef) -> str:
        params_str = ", ".join(f"{k}: {v}" for k, v in tool.parameters.items()) if tool.parameters else "**kwargs: Any"
        triggers_str = repr(tool.auto_triggers)

        return (
            f'"""\n{tool.description}\nAuto-triggers: {triggers_str}\n"""\n'
            f"from typing import Any\n\n\n"
            f"def {tool.name}({params_str}) -> Any:\n"
            f'    """{tool.description}"""\n'
            f"    raise NotImplementedError(\"Tool body not yet generated\")\n"
        )

    def tool_count_by_source(self) -> dict[str, int]:
        counts = {}
        for t in self._tools.values():
            counts[t.source] = counts.get(t.source, 0) + 1
        return counts

    def get_tool_descriptions(self) -> str:
        lines = []
        for t in sorted(self._tools.values(), key=lambda x: x.name):
            params = ", ".join(f"{k}: {v}" for k, v in t.parameters.items()) if t.parameters else "—"
            lines.append(f"  {t.name:20s}  {t.description:50s}  ({t.source})")
        return "\n".join(lines)
