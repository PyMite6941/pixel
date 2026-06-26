import webbrowser
from typing import Any

from skills.base_skill import BaseSkill


class Browser(BaseSkill):
    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return "Open URLs in the default web browser, or search the web"

    @property
    def auto_triggers(self) -> list[str]:
        return ["open browser", "open url", "open website", "go to", "launch browser", "navigate to"]

    def execute(self, action: str = "open", url: str = "", query: str = "", **kwargs: Any) -> str:
        if action == "open":
            if not url:
                return "Missing 'url' parameter"
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            webbrowser.open(url)
            return f"Opened {url} in default browser"
        elif action == "search":
            if not query:
                return "Missing 'query' parameter"
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            webbrowser.open(search_url)
            return f"Searched for '{query}' in default browser"
        return f"Unknown action: {action}. Use: open, search"
