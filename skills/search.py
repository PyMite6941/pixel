import os
import re
import urllib.parse
from html.parser import HTMLParser

import requests


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


class Search:
    def __init__(self, query: str, search_engine: str = None):
        self.query = query
        engine = (search_engine or os.getenv("SEARCH_ENGINE", "duckduckgo")).lower()
        self._method = {
            "google": self._google,
            "bing": self._bing,
        }.get(engine, self._duckduckgo)

    def run(self) -> str:
        return self._method()

    def _google(self) -> str:
        url = f"https://www.google.com/search?q={urllib.parse.quote(self.query)}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        return _extract_text(resp.text)

    def _bing(self) -> str:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(self.query)}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        return _extract_text(resp.text)

    def _duckduckgo(self) -> str:
        url = f"https://duckduckgo.com/html/?q={urllib.parse.quote(self.query)}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        return _extract_text(resp.text)
