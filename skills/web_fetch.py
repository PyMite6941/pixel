from typing import Any

import requests

from skills.base_skill import BaseSkill


class WebFetch(BaseSkill):
    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch a URL and return its content as text (HTML stripped)"

    @property
    def auto_triggers(self) -> list[str]:
        return ["fetch url", "fetch website", "get url", "download page", "read website", "open url", "http get"]

    def execute(self, url: str, timeout: int = 15, **kwargs: Any) -> str:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=timeout,
            )
            if resp.status_code != 200:
                return f"HTTP {resp.status_code}: {resp.reason}"
            text = resp.text
            if len(text) > 20000:
                text = text[:20000] + f"\n... (truncated, {len(text)} total chars)"
            return text
        except requests.exceptions.Timeout:
            return f"Request timed out after {timeout} seconds"
        except requests.exceptions.ConnectionError:
            return f"Could not connect to {url}"
        except Exception as e:
            return f"Fetch failed: {e}"
