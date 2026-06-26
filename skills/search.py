import os
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any

import requests

from skills.base_skill import BaseSkill


class _HTMLToText(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._text.append(data.strip())

    def get_text(self) -> str:
        return " ".join(t for t in self._text if t)


def _extract_text(html: str) -> str:
    parser = _HTMLToText()
    parser.feed(html)
    text = parser.get_text()
    text = re.sub(r"\s+", " ", text).strip()
    lines = [line.strip() for line in text.split(". ") if line.strip()]
    return ".\n".join(lines[:20])


class Search(BaseSkill):
    @property
    def name(self) -> str:
        return "search"

    @property
    def description(self) -> str:
        return "Search the web using Google, Bing, or DuckDuckGo"

    @property
    def auto_triggers(self) -> list[str]:
        return ["search for", "search the web", "look up", "find online", "google", "what is", "who is", "tell me about"]

    @property
    def requires_subprocess(self) -> bool:
        return True

    def execute(self, query: str, engine: str | None = None, **kwargs: Any) -> str:
        engine = engine or os.getenv("SEARCH_ENGINE", "duckduckgo")
        method = {
            "google": self._google,
            "bing": self._bing,
        }.get(engine.lower(), self._duckduckgo)
        return method(query)

    def _google(self, query: str) -> str:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        return _extract_text(resp.text)

    def _bing(self, query: str) -> str:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        return _extract_text(resp.text)

    def _duckduckgo(self, query: str) -> str:
        url = f"https://duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        return _extract_text(resp.text)
