import textwrap
from typing import Any, Optional
from .registry import DynamicToolRegistry, ToolDef


class ToolGenerator:
    """Generates new tool code using an LLM, then registers it dynamically."""

    def __init__(self, registry: DynamicToolRegistry, llm_ask):
        self.registry = registry
        self.llm_ask = llm_ask

    def generate_tool(self, name: str, description: str,
                      parameters: dict[str, str] = None) -> ToolDef:
        existing_tools = self.registry.get_tool_descriptions()
        prompt = (
            f"Generate a Python tool function called '{name}'.\n\n"
            f"Description: {description}\n"
            f"Parameters: {parameters or {}}\n\n"
            f"Existing tools available to this system:\n{existing_tools}\n\n"
            f"If this tool can be built by combining existing tools, list them in a comment.\n"
            f"Otherwise, generate a complete, working Python function.\n\n"
            f"Rules:\n"
            f"- Use only standard library + requests if needed\n"
            f"- Include proper error handling\n"
            f"- Keep it under 50 lines\n"
            f"- Return a string result\n"
            f"- Import anything needed inside the function\n\n"
            f"Return ONLY the Python code, no explanations."
        )

        code = self.llm_ask(prompt)
        code = self._clean_code(code)

        tool = ToolDef(
            name=name,
            description=description,
            parameters=parameters or {},
            code=code,
            source="generated",
        )
        self.registry.register_tool(tool)
        return tool

    def _clean_code(self, code: str) -> str:
        lines = code.strip().split("\n")
        cleaned = []
        in_code = False
        for line in lines:
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                cleaned.append(line)
        if not cleaned:
            cleaned = [l for l in lines if not l.startswith("#") and l.strip()]
        result = "\n".join(cleaned).strip()
        if result.startswith("python"):
            result = result[6:].strip()
        return result
