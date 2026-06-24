from brain.domains.base_domain import BaseDomain


class CodingDomain(BaseDomain):
    keywords = [
        "code", "function", "bug", "error", "debug", "script", "program",
        "python", "javascript", "java", "c++", "rust", "go", "algorithm",
        "class", "method", "variable", "loop", "import", "syntax",
    ]

    def encode(self, context: dict) -> dict:
        task = str(context.get("task", "")).lower()
        lang = "unknown"
        for candidate in ("python", "javascript", "java", "c++", "rust", "go"):
            if candidate in task:
                lang = candidate
                break
        return {
            "domain": "coding",
            "language": lang,
            "task": task,
        }
