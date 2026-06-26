"""
test tool
Pipeline: think, search
"""
from typing import Any


def s_and_f(**kwargs: Any) -> Any:
    """test tool"""
    pipeline = ["think",
        "search"]
    results = {}
    for tool_name in pipeline:
        tool = registry.get_tool(tool_name)
        if not tool:
            return f"Tool {tool_name} not found"
        results[tool_name] = kwargs.get(tool_name)
    return results
