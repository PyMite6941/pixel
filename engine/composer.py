from typing import Any, Optional
from .registry import DynamicToolRegistry, ToolDef


class ToolComposer:
    """Compose new tools by combining existing ones."""

    def __init__(self, registry: DynamicToolRegistry):
        self.registry = registry

    def compose(self, name: str, description: str, pipeline: list[str],
                parameters: dict[str, str] = None) -> ToolDef:
        for tool_name in pipeline:
            if not self.registry.get_tool(tool_name):
                raise ValueError(f"Tool '{tool_name}' not found in registry")

        pipeline_tools = [self.registry.get_tool(t) for t in pipeline]
        pipeline_desc = " → ".join(t.name for t in pipeline_tools)

        code = self._generate_composite_code(name, description, pipeline, parameters or {})

        tool = ToolDef(
            name=name,
            description=f"{description} (composed: {pipeline_desc})",
            parameters=parameters or self._merge_params(pipeline_tools),
            code=code,
            is_composite=True,
            source="composed",
        )
        self.registry.register_tool(tool)
        return tool

    def _merge_params(self, tools: list[ToolDef]) -> dict[str, str]:
        params = {}
        for t in tools:
            params.update(t.parameters)
        return params

    def _generate_composite_code(self, name: str, description: str,
                                  pipeline: list[str], params: dict[str, str]) -> str:
        pipes = ",\n        ".join(f'"{t}"' for t in pipeline)
        return (
            f'"""\n{description}\nPipeline: {", ".join(pipeline)}\n"""\n'
            f"from typing import Any\n\n\n"
            f"def {name}(**kwargs: Any) -> Any:\n"
            f'    """{description}"""\n'
            f"    pipeline = [{pipes}]\n"
            f"    results = {{}}\n"
            f"    for tool_name in pipeline:\n"
            f"        tool = registry.get_tool(tool_name)\n"
            f"        if not tool:\n"
            f'            return f"Tool {{tool_name}} not found"\n'
            f"        results[tool_name] = kwargs.get(tool_name)\n"
            f"    return results\n"
        )
