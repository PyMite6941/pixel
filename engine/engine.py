import time
from typing import Any, Optional
from .registry import DynamicToolRegistry, ToolDef
from .planner import Planner, PlanStep
from .composer import ToolComposer
from .generator import ToolGenerator
from .trainer import EngineTrainer


class SmartEngine:
    """Autonomous AI engine that discovers, selects, composes, and generates tools."""

    def __init__(self, pixel_instance=None, llm_ask=None):
        from skills.registry import SkillRegistry
        self._pixel = pixel_instance
        self._skills = pixel_instance.skills if pixel_instance else SkillRegistry()
        self.registry = DynamicToolRegistry(self._skills)
        self.planner = Planner()
        self.composer = ToolComposer(self.registry)
        self.generator = ToolGenerator(self.registry, llm_ask or self._default_ask)
        self.trainer = EngineTrainer(self.registry, llm_ask or self._default_ask)
        self._execution_history: list[dict] = []
        self._llm_ask = llm_ask or self._default_ask

    def _default_ask(self, prompt: str) -> str:
        if self._pixel:
            return self._pixel.ask(prompt)
        return "[No LLM available]"

    # --- Tool Usage ---

    def find_tools_for(self, task: str) -> list[ToolDef]:
        results = self.trainer.find_best_tools(task, top_k=5)
        tools = []
        for r in results:
            t = self.registry.get_tool(r["tool"] if isinstance(r, dict) else r)
            if t:
                tools.append(t)
        return tools

    def use_tool(self, tool_name: str, **params) -> Any:
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return f"Tool '{tool_name}' not found"
        if self._skills and tool.name in self._skills.skill_names:
            return self._skills.run(tool.name, **params)
        if tool.code:
            return self._run_generated_code(tool, **params)
        return f"Tool '{tool_name}' has no executable code"

    def _run_generated_code(self, tool: ToolDef, **params) -> Any:
        try:
            local_ns = {"registry": self.registry, "result": None}
            exec(tool.code, local_ns)
            if tool.name in local_ns:
                return local_ns[tool.name](**params)
            return local_ns.get("result", "Tool executed (no return value)")
        except Exception as e:
            return f"Tool '{tool.name}' execution failed: {e}"

    # --- Planning & Execution ---

    def execute(self, task: str, auto_synthesize: bool = True) -> str:
        tools = self.trainer.find_best_tools(task)
        chain = self.trainer.suggest_tool_chains(task)
        if chain:
            steps = [PlanStep(
                step_id=i + 1, action=t, tool=t,
                params={"task": task}, description=f"Execute {t}"
            ) for i, t in enumerate(chain)]
            steps.append(PlanStep(
                step_id=len(steps) + 1, action="synthesize", tool="think",
                params={"task": task}, description="Synthesize results",
                depends_on=list(range(1, len(steps) + 1)),
            ))
        else:
            steps = self.planner.plan(task, tools)
        start = time.time()
        result = self._execute_plan(task, steps, auto_synthesize)
        duration = time.time() - start
        success = "error" not in result.lower()[:100]
        self.trainer.learn_from_execution(task, steps=[s.__dict__ for s in steps],
                                          success=success, duration=duration)
        return result

    def execute_with_llm_plan(self, task: str) -> str:
        descriptions = self.registry.get_tool_descriptions()
        steps = self.planner.plan_from_llm(task, descriptions, self._llm_ask)
        return self._execute_plan(task, steps, auto_synthesize=True)

    def _execute_plan(self, task: str, steps: list[PlanStep], auto_synthesize: bool) -> str:
        results: dict[int, Any] = {}
        execution_log = []

        for step in steps:
            deps_met = all(d in results for d in step.depends_on)
            if not deps_met:
                step.status = "skipped"
                execution_log.append({"step": step.step_id, "tool": step.tool, "status": "skipped", "reason": "dependencies not met"})
                continue

            step.status = "running"
            try:
                params = dict(step.params)
                for dep_id in step.depends_on:
                    if dep_id in results:
                        params[f"result_from_step_{dep_id}"] = str(results[dep_id])

                result = self.use_tool(step.tool, **params)
                step.result = result
                step.status = "done"
                results[step.step_id] = result
            except Exception as e:
                step.error = str(e)
                step.status = "failed"
                result = f"Error: {e}"

            execution_log.append({
                "step": step.step_id,
                "tool": step.tool,
                "action": step.action,
                "status": step.status,
                "result": str(result)[:500] if result else None,
                "error": step.error,
            })

        self._execution_history.append({
            "task": task,
            "timestamp": time.time(),
            "steps": execution_log,
            "completed": any(s.status == "done" for s in steps),
        })

        if auto_synthesize:
            return self._synthesize(task, execution_log, results)
        return execution_log

    def _synthesize(self, task: str, log: list[dict], results: dict[int, Any]) -> str:
        context_parts = [f"Task: {task}", ""]
        for entry in log:
            if entry["status"] == "done" and entry.get("result"):
                context_parts.append(f"[{entry['tool']}] {entry['result'][:1000]}")

        context = "\n".join(context_parts)
        prompt = (
            f"Based on these tool results, provide a complete answer to the original task.\n\n"
            f"{context}\n\n"
            f"Answer concisely and directly."
        )
        return self._llm_ask(prompt)

    # --- Tool Generation ---

    def suggest_new_tool(self, description: str, parameters: dict[str, str] = None) -> Optional[ToolDef]:
        import re
        name = "custom_" + re.sub(r'[^a-z0-9]', '_', description.lower().split()[0])[:20]
        return self.generator.generate_tool(name, description, parameters)

    def compose_tool(self, name: str, description: str, pipeline: list[str],
                     parameters: dict[str, str] = None) -> ToolDef:
        return self.composer.compose(name, description, pipeline, parameters)

    # --- Introspection ---

    def get_stats(self) -> dict:
        return {
            "total_tools": len(self.registry.list_tools()),
            "by_source": self.registry.tool_count_by_source(),
            "executions": len(self._execution_history),
            "tools_trained": self.trainer.get_training_status()["tools_trained"],
            "execution_patterns": self.trainer.get_training_status()["execution_patterns"],
            "recent_tasks": [e["task"][:80] for e in self._execution_history[-5:]],
        }

    def get_tool_report(self) -> str:
        lines = ["Smart Engine — Tool Report", "=" * 40]
        lines.append(f"Total tools: {len(self.registry.list_tools())}")
        for source, count in self.registry.tool_count_by_source().items():
            lines.append(f"  {source}: {count}")
        lines.append(f"Trained: {self.trainer.get_training_status()['tools_trained']} tools")
        lines.append(f"Patterns: {self.trainer.get_training_status()['execution_patterns']} executions")
        lines.append("")
        lines.append(self.trainer.generate_tool_catalog())
        lines.append(self.registry.get_tool_descriptions())
        return "\n".join(lines)
