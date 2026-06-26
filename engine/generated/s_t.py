"""
test
Pipeline: search, think
"""
from typing import Any


def s_t(**kwargs: Any) -> Any:
    """test"""
    pipeline = ["search",
        "think"]
    results = {}
    for tool_name in pipeline:
        tool = registry.get_tool(tool_name)
        if not tool:
            return f"Tool {tool_name} not found"
        results[tool_name] = kwargs.get(tool_name)
    return results
