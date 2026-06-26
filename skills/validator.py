import ast
from typing import Any

from skills.base_skill import BaseSkill


class Validator(BaseSkill):
    @property
    def name(self) -> str:
        return "validator"

    @property
    def description(self) -> str:
        return "Validate Python syntax, check for common issues, and lint code"

    def execute(self, code: str, check: str = "syntax", **kwargs: Any) -> str:
        if check == "syntax":
            return self._check_syntax(code)
        if check == "imports":
            return self._check_imports(code)
        return f"Unknown check: {check}. Use: syntax, imports"

    def _check_syntax(self, code: str) -> str:
        try:
            tree = ast.parse(code)
            lines = code.strip().split("\n")
            return (
                f"Syntax: OK\n"
                f"Lines: {len(lines)}\n"
                f"AST nodes: {len(list(ast.walk(tree)))}\n"
                f"Type: {'expression' if len(lines) == 1 and not code.strip().endswith(':') else 'statement block'}"
            )
        except SyntaxError as e:
            return f"Syntax Error:\n  Line {e.lineno}, col {e.offset}: {e.msg}\n  Text: {e.text.strip() if e.text else 'N/A'}"

    def _check_imports(self, code: str) -> str:
        try:
            tree = ast.parse(code)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}" if module else alias.name)

            if not imports:
                return "No imports found."

            results = []
            for imp in imports:
                try:
                    top = imp.split(".")[0]
                    __import__(top)
                    results.append(f"  [OK] {imp}")
                except ImportError:
                    results.append(f"  [MISSING] {imp}")

            return "Import check:\n" + "\n".join(results)
        except SyntaxError as e:
            return f"Cannot check imports — code has syntax error: {e.msg}"
