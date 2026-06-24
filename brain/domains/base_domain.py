from abc import ABC, abstractmethod


class BaseDomain(ABC):
    keywords: list[str] = []

    @abstractmethod
    def encode(self, context: dict) -> dict:
        pass

    def matches(self, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in self.keywords)
