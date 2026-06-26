"""
Search then fetch
Pipeline: search, web_fetch
"""
from typing import Any


def search_fetch(**kwargs: Any) -> Any:
    """Search then fetch"""
    pipeline = ["search",
        "web_fetch"]
    results = {}
    for tool_name in pipeline:
        tool = registry.get_tool(tool_name)
        if not tool:
            return f"Tool {tool_name} not found"
        results[tool_name] = kwargs.get(tool_name)
    return results
