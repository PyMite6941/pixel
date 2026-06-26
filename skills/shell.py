import subprocess
import sys
from typing import Any

from skills.base_skill import BaseSkill


class Shell(BaseSkill):
    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "Run shell commands (PowerShell, cmd, or Python) with output capture and timeout"

    @property
    def auto_triggers(self) -> list[str]:
        return ["run command", "execute", "shell", "terminal", "powershell", "cmd", "command line", "run in terminal"]

    def execute(self, command: str, shell_type: str = "powershell", timeout: int = 30, **kwargs: Any) -> str:
        if shell_type == "powershell":
            executable = "powershell"
            args = ["-NoProfile", "-"]
            input_data = command
        elif shell_type == "cmd":
            executable = "cmd"
            args = ["/c", command]
            input_data = None
        elif shell_type == "python":
            executable = sys.executable
            args = ["-c", command]
            input_data = None
        else:
            return f"Unsupported shell: {shell_type}. Use: powershell, cmd, python"

        try:
            result = subprocess.run(
                [executable, *args],
                input=input_data, capture_output=True, text=True, timeout=timeout,
            )
            output = result.stdout if result.returncode == 0 else result.stderr
            if not output:
                return f"Command completed (exit code {result.returncode}) with no output"
            if len(output) > 10000:
                output = output[:10000] + f"\n... (truncated, {len(output)} total chars)"
            return output.strip()
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout} seconds"
        except FileNotFoundError:
            return f"Shell executable not found: {executable}"
        except Exception as e:
            return f"Command failed: {e}"
