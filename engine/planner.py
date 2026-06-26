from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PlanStep:
    step_id: int
    action: str
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    depends_on: list[int] = field(default_factory=list)
    status: str = "pending"  # pending, running, done, failed
    result: Optional[Any] = None
    error: Optional[str] = None


class Planner:
    """Breaks tasks into steps and assigns tools to each step."""

    def plan(self, task: str, available_tools: list) -> list[PlanStep]:
        task_lower = task.lower()
        steps: list[PlanStep] = []

        has_code = any(kw in task_lower for kw in ("code", "function", "script", "program", "python", "javascript"))
        has_search = any(kw in task_lower for kw in ("search", "find", "look up", "what is", "who is", "google"))
        has_file = any(kw in task_lower for kw in ("file", "write", "save", "read", "create"))
        has_web = any(kw in task_lower for kw in ("fetch", "website", "url", "http", "https://", "download"))
        has_shell = any(kw in task_lower for kw in ("run", "execute", "command", "shell", "terminal"))
        has_reasoning = any(kw in task_lower for kw in ("think", "reason", "analyze", "compare", "evaluate", "why"))

        step_id = 0

        if has_reasoning:
            step_id += 1
            steps.append(PlanStep(
                step_id=step_id, action="reason", tool="think",
                params={"task": task},
                description="Break down the task into reasoning steps",
            ))

        if has_search:
            step_id += 1
            query = task
            if ":" in task:
                parts = task.split(":", 1)
                if len(parts) == 2:
                    query = parts[1].strip()
            steps.append(PlanStep(
                step_id=step_id, action="search", tool="search",
                params={"query": query},
                description=f"Search the web for: {query}",
            ))

        if has_web:
            step_id += 1
            steps.append(PlanStep(
                step_id=step_id, action="fetch", tool="web_fetch",
                params={"url": task if task.startswith(("http://", "https://")) else ""},
                description="Fetch web content",
                depends_on=[step_id - 1] if step_id > 1 and has_search else [],
            ))

        if has_code:
            step_id += 1
            steps.append(PlanStep(
                step_id=step_id, action="code", tool="run_code",
                params={"code": task},
                description="Execute or analyze code",
                depends_on=[step_id - 1] if step_id > 1 and (has_search or has_web) else [],
            ))

        if has_file:
            step_id += 1
            steps.append(PlanStep(
                step_id=step_id, action="file_ops", tool="file_ops",
                params={"task": task},
                description="Perform file operations",
                depends_on=[step_id - 1] if step_id > 1 and has_code else [],
            ))

        if has_shell:
            step_id += 1
            steps.append(PlanStep(
                step_id=step_id, action="shell", tool="shell",
                params={"command": task},
                description="Execute shell command",
            ))

        if not steps:
            step_id += 1
            steps.append(PlanStep(
                step_id=step_id, action="think", tool="think",
                params={"task": task},
                description="Analyze and respond to the task",
            ))

        step_id += 1
        steps.append(PlanStep(
            step_id=step_id, action="synthesize", tool="think",
            params={"task": task, "previous_results": [s.result for s in steps if s.result is not None]},
            description="Synthesize all results into final response",
            depends_on=[s.step_id for s in steps],
        ))

        return steps

    def plan_from_llm(self, task: str, tool_descriptions: str, llm_ask) -> list[PlanStep]:
        prompt = (
            f"Given this task: '{task}'\n\n"
            f"Available tools:\n{tool_descriptions}\n\n"
            f"Create a plan as a numbered list of steps. Each step should specify:\n"
            f"- Which tool to use\n"
            f"- What parameters to pass\n"
            f"- Which steps it depends on (by number)\n\n"
            f"Format each line as: STEP <n>: TOOL <tool_name> | PARAMS: <json_params> | DEPENDS: [<step_numbers>] | DESC: <description>\n"
            f"Keep the plan focused and minimal."
        )
        reply = llm_ask(prompt)
        return self._parse_llm_plan(reply)

    def _parse_llm_plan(self, text: str) -> list[PlanStep]:
        import json, re
        steps = []
        for line in text.strip().split("\n"):
            m = re.match(r"STEP\s+(\d+):\s*TOOL\s+(\w+)\s*\|\s*PARAMS:\s*(\{.*?\})\s*\|\s*DEPENDS:\s*(\[.*?\])\s*\|\s*DESC:\s*(.+)", line, re.IGNORECASE)
            if m:
                step_id = int(m.group(1))
                tool = m.group(2).lower()
                try:
                    params = json.loads(m.group(3))
                except json.JSONDecodeError:
                    params = {}
                depends = json.loads(m.group(4))
                desc = m.group(5).strip()
                steps.append(PlanStep(
                    step_id=step_id, action=tool, tool=tool,
                    params=params, description=desc, depends_on=depends,
                ))
        return steps
