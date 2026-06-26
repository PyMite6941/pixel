import subprocess
from typing import Any

from skills.base_skill import BaseSkill


class RunCode(BaseSkill):
    @property
    def name(self) -> str:
        return "run_code"

    @property
    def description(self) -> str:
        return "Execute Python code in a subprocess with a 5-second timeout"

    @property
    def auto_triggers(self) -> list[str]:
        return ["run this code", "execute python", "run python", "eval", "subprocess"]

    @property
    def requires_subprocess(self) -> bool:
        return True

    def execute(self, code: str, language: str = "python", **kwargs: Any) -> str:
        if language != "python":
            return f"Unsupported language: {language}"
        try:
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout if result.returncode == 0 else result.stderr
        except subprocess.TimeoutExpired:
            return "Execution timed out after 5 seconds"
        except Exception as e:
            return f"Execution failed: {e}"
