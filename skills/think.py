import json
from typing import Any

from skills.base_skill import BaseSkill


class Think(BaseSkill):
    @property
    def name(self) -> str:
        return "think"

    @property
    def description(self) -> str:
        return "Break down a complex task into structured reasoning steps"

    @property
    def auto_triggers(self) -> list[str]:
        return ["think step by step", "break down", "reason", "plan", "steps to", "how would you", "strategy"]

    def execute(self, task: str, **kwargs: Any) -> str:
        steps = self._decompose(task)
        lines = []
        lines.append(f"Task: {task}")
        lines.append(f"Estimated complexity: {steps['complexity']}")
        lines.append(f"Number of steps: {len(steps['steps'])}")
        lines.append("")
        for i, step in enumerate(steps["steps"], 1):
            lines.append(f"Step {i}: {step}")
        lines.append("")
        lines.append("Dependencies:")
        for dep in steps["dependencies"]:
            lines.append(f"  - {dep}")
        return "\n".join(lines)

    def _decompose(self, task: str) -> dict:
        task_lower = task.lower()
        words = task_lower.split()
        word_count = len(words)

        if word_count <= 5:
            complexity = "simple"
            steps = ["Understand the request", "Execute and return result"]
            dependencies = []
        elif word_count <= 15:
            complexity = "moderate"
            steps = [
                "Clarify the request and identify key requirements",
                "Gather needed information or resources",
                "Process and generate output",
                "Validate the result",
            ]
            dependencies = ["None identified"]
        else:
            complexity = "complex"
            steps = [
                "Parse and decompose the request into sub-tasks",
                "Identify dependencies between sub-tasks",
                "Execute sub-tasks in dependency order",
                "Synthesize partial results",
                "Validate final output against requirements",
            ]
            dependencies = []

        if any(kw in task_lower for kw in ("code", "function", "script", "program")):
            steps.append("Run syntax validation on generated code")
            dependencies.append("Syntax validator")
        if any(kw in task_lower for kw in ("api", "token", "key", "secret")):
            steps.append("Scan for secrets before any output")
            dependencies.append("Secret scanner")
        if any(kw in task_lower for kw in ("file", "write", "update", "modify")):
            steps.append("Create backup before modifications")
            dependencies.append("File system access")

        return {
            "complexity": complexity,
            "steps": steps,
            "dependencies": list(set(dependencies)),
        }
