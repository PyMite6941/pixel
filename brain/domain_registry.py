from brain.domains.coding import CodingDomain
from brain.domains.game import GameDomain


_DOMAINS = [
    CodingDomain(),
    GameDomain(),
]


class DomainRegistry:
    def route(self, text: str) -> str:
        for domain in _DOMAINS:
            if domain.matches(text):
                return type(domain).__name__
        return "GeneralDomain"

    def encode(self, text: str) -> dict:
        for domain in _DOMAINS:
            if domain.matches(text):
                return domain.encode({"task": text})
        return {"domain": "general", "task": text}
