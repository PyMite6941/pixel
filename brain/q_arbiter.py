from brain.domain_registry import DomainRegistry

_registry = DomainRegistry()


def route(question: str) -> str:
    return _registry.route(question)


def encode(question: str) -> dict:
    return _registry.encode(question)
