import subprocess
from typing import Any

from skills.base_skill import BaseSkill


class Clipboard(BaseSkill):
    @property
    def name(self) -> str:
        return "clipboard"

    @property
    def description(self) -> str:
        return "Read or write the system clipboard"

    @property
    def auto_triggers(self) -> list[str]:
        return ["clipboard", "copy to clipboard", "paste from clipboard", "clip", "get clipboard"]

    def execute(self, action: str = "read", text: str | None = None, **kwargs: Any) -> str:
        if action == "read":
            return self._read()
        elif action == "write":
            if text is None:
                return "Missing 'text' parameter for write action"
            return self._write(text)
        return f"Unknown action: {action}. Use: read, write"

    def _read(self) -> str:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                content = result.stdout.strip()
                return content if content else "(empty clipboard)"
            return f"Failed to read clipboard: {result.stderr.strip()}"
        except Exception as e:
            return f"Clipboard read failed: {e}"

    def _write(self, text: str) -> str:
        import base64
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        script = (
            '$text = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("'
            + encoded
            + '"))\n'
            "Set-Clipboard -Value $text\n"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-"],
                input=script, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return f"Copied {len(text)} chars to clipboard"
            return f"Failed to write clipboard: {result.stderr.strip()}"
        except Exception as e:
            return f"Clipboard write failed: {e}"
