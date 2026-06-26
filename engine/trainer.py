import json
import time
from pathlib import Path
from typing import Optional
from .registry import DynamicToolRegistry, ToolDef


TRAINING_DIR = Path(__file__).parent / "training_data"
TRAINING_DIR.mkdir(exist_ok=True)

_TOOL_KNOWLEDGE_FILE = TRAINING_DIR / "tool_knowledge.json"
_EXECUTION_PATTERNS_FILE = TRAINING_DIR / "execution_patterns.json"


class EngineTrainer:
    """Trains the Smart Engine on all available tools — analyzes, understands, and optimizes tool usage."""

    def __init__(self, registry: DynamicToolRegistry, llm_ask=None):
        self.registry = registry
        self._llm_ask = llm_ask
        self._knowledge: dict[str, dict] = {}
        self._patterns: list[dict] = []
        self._load()

    def _load(self):
        if _TOOL_KNOWLEDGE_FILE.exists():
            try:
                self._knowledge = json.loads(_TOOL_KNOWLEDGE_FILE.read_text())
            except Exception:
                self._knowledge = {}
        if _EXECUTION_PATTERNS_FILE.exists():
            try:
                self._patterns = json.loads(_EXECUTION_PATTERNS_FILE.read_text())
            except Exception:
                self._patterns = []

    def _save(self):
        _TOOL_KNOWLEDGE_FILE.write_text(json.dumps(self._knowledge, indent=2))
        _EXECUTION_PATTERNS_FILE.write_text(json.dumps(self._patterns, indent=2))

    # --- Training ---

    def train_on_all_tools(self) -> dict:
        tools = self.registry.list_tools()
        results = {"trained": 0, "errors": 0, "details": []}

        for tool in tools:
            try:
                knowledge = self._analyze_tool(tool)
                self._knowledge[tool.name] = knowledge
                results["trained"] += 1
                results["details"].append({"tool": tool.name, "status": "ok", "use_cases": len(knowledge.get("use_cases", []))})
            except Exception as e:
                results["errors"] += 1
                results["details"].append({"tool": tool.name, "status": "error", "error": str(e)})

        self._generate_tool_relationships()
        self._save()
        results["total_tools"] = len(tools)
        return results

    def _analyze_tool(self, tool: ToolDef, depth: str = "full") -> dict:
        if not self._llm_ask:
            return self._basic_analysis(tool)

        prompt = (
            f"Analyze this tool in depth:\n\n"
            f"Name: {tool.name}\n"
            f"Description: {tool.description}\n"
            f"Parameters: {tool.parameters}\n"
            f"Auto-triggers: {tool.auto_triggers}\n"
            f"Source: {tool.source}\n"
            f"Code:\n{tool.code or 'N/A'}\n\n"
            f"Return a JSON object with these fields:\n"
            f"  \"summary\": one-sentence summary of what this tool does\n"
            f"  \"capabilities\": list of specific things this tool can do (be specific)\n"
            f"  \"use_cases\": list of example tasks this tool is good for (3-5 examples)\n"
            f"  \"when_to_use\": when should the engine choose this tool\n"
            f"  \"when_not_to_use\": when should the engine avoid this tool\n"
            f"  \"required_params\": which params are required vs optional\n"
            f"  \"similar_tools\": other tools that do similar things\n"
            f"  \"chaining\": what tools commonly chain before or after this one\n"
            f"  \"keywords\": important keywords (comma-separated)\n\n"
            f"Return ONLY valid JSON, no other text."
        )

        try:
            reply = self._llm_ask(prompt)
            import re
            json_match = re.search(r'\{.*\}', reply, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass

        return self._basic_analysis(tool)

    def _basic_analysis(self, tool: ToolDef) -> dict:
        return {
            "summary": tool.description,
            "capabilities": [tool.description],
            "use_cases": [f"Use {tool.name} when you need to {tool.description.lower()}"],
            "when_to_use": f"When the task involves {tool.description.lower()}",
            "when_not_to_use": "",
            "required_params": tool.parameters,
            "similar_tools": [],
            "chaining": {"before": [], "after": []},
            "keywords": tool.name + ", " + tool.description,
        }

    def _generate_tool_relationships(self):
        for name, knowledge in self._knowledge.items():
            keywords = knowledge.get("keywords", "").lower()
            similar = []
            for other_name, other_knowledge in self._knowledge.items():
                if other_name == name:
                    continue
                other_keywords = other_knowledge.get("keywords", "").lower()
                shared = set(keywords.split(", ")) & set(other_keywords.split(", "))
                if len(shared) > 1:
                    similar.append(other_name)
            if similar:
                knowledge["related_tools"] = similar

    # --- Semantic Tool Selection ---

    def find_best_tools(self, task: str, top_k: int = 5) -> list[dict]:
        if self._llm_ask and self._knowledge:
            return self._llm_tool_select(task, top_k)
        return self._keyword_tool_select(task, top_k)

    def _keyword_tool_select(self, task: str, top_k: int) -> list[dict]:
        task_lower = task.lower()
        scored = []
        for name, knowledge in self._knowledge.items():
            score = 0
            keywords = knowledge.get("keywords", "").lower()
            for kw in keywords.split(", "):
                kw = kw.strip()
                if kw and kw in task_lower:
                    score += 1
            for uc in knowledge.get("use_cases", []):
                uc_lower = uc.lower()
                common = len(set(task_lower.split()) & set(uc_lower.split()))
                score += common * 0.5
            if score > 0:
                scored.append({"tool": name, "score": score, "knowledge": knowledge})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _llm_tool_select(self, task: str, top_k: int) -> list[dict]:
        knowledge_summary = "\n".join(
            f"- {name}: {k['summary']} | use cases: {'; '.join(k.get('use_cases', [])[:2])}"
            for name, k in self._knowledge.items()
        )
        prompt = (
            f"Given this task: \"{task}\"\n\n"
            f"Available tools and their capabilities:\n{knowledge_summary}\n\n"
            f"Return a JSON array of the top {top_k} most relevant tools.\n"
            f"Each entry: {{\"tool\": \"name\", \"reason\": \"why it's relevant\"}}\n"
            f"Return ONLY the JSON array, no other text."
        )
        try:
            reply = self._llm_ask(prompt)
            import re
            import json
            array_match = re.search(r'\[.*\]', reply, re.DOTALL)
            if array_match:
                results = json.loads(array_match.group())
                for r in results:
                    r["knowledge"] = self._knowledge.get(r["tool"], {})
                return results[:top_k]
        except Exception:
            pass
        return self._keyword_tool_select(task, top_k)

    # --- Execution Pattern Learning ---

    def learn_from_execution(self, task: str, steps: list[dict], success: bool, duration: float):
        pattern = {
            "task": task,
            "task_category": self._categorize_task(task),
            "steps": [{"tool": s.get("tool"), "action": s.get("action"), "status": s.get("status")} for s in steps],
            "success": success,
            "duration": duration,
            "timestamp": time.time(),
        }
        self._patterns.append(pattern)
        if len(self._patterns) > 1000:
            self._patterns = self._patterns[-500:]
        self._save()

    def _categorize_task(self, task: str) -> str:
        t = task.lower()
        if any(kw in t for kw in ("code", "script", "function", "python", "program")):
            return "coding"
        if any(kw in t for kw in ("search", "find", "look up", "what is")):
            return "research"
        if any(kw in t for kw in ("file", "write", "read", "save", "create")):
            return "file_management"
        if any(kw in t for kw in ("analyze", "compare", "evaluate", "why")):
            return "analysis"
        if any(kw in t for kw in ("run", "execute", "command", "shell")):
            return "execution"
        return "general"

    def suggest_tool_chains(self, task: str) -> list[str]:
        category = self._categorize_task(task)
        relevant = [p for p in self._patterns if p["task_category"] == category and p["success"]]
        if not relevant:
            return []

        from collections import Counter
        chains = Counter()
        for p in relevant:
            tool_seq = tuple(s["tool"] for s in p["steps"] if s["status"] == "done")
            if tool_seq:
                chains[tool_seq] += 1
        if chains:
            return list(chains.most_common(3)[0][0])
        return []

    def get_training_status(self) -> dict:
        return {
            "tools_trained": len(self._knowledge),
            "execution_patterns": len(self._patterns),
            "total_tools": len(self.registry.list_tools()),
            "knowledge_file": str(_TOOL_KNOWLEDGE_FILE),
            "patterns_file": str(_EXECUTION_PATTERNS_FILE),
        }

    def generate_tool_catalog(self) -> str:
        lines = ["=" * 60, "SMART ENGINE — TRAINED TOOL CATALOG", "=" * 60, ""]
        for name in sorted(self._knowledge.keys()):
            k = self._knowledge[name]
            lines.append(f"[{name}]")
            lines.append(f"  Summary: {k.get('summary', 'N/A')}")
            use_cases = k.get("use_cases", [])
            if use_cases:
                lines.append(f"  Best for: {use_cases[0]}")
            related = k.get("related_tools", [])
            if related:
                lines.append(f"  Related: {', '.join(related[:3])}")
            lines.append("")
        return "\n".join(lines)
