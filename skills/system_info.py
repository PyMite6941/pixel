import os
import platform
import shutil
from pathlib import Path
from typing import Any

from skills.base_skill import BaseSkill

_ROOT = Path(__file__).parent.parent.resolve()


class SystemInfo(BaseSkill):
    @property
    def name(self) -> str:
        return "system_info"

    @property
    def description(self) -> str:
        return "Report OS, Python version, disk space, and environment details"

    @property
    def auto_triggers(self) -> list[str]:
        return ["system info", "system information", "what os", "python version", "disk space", "environment", "specs"]

    def execute(self, **kwargs: Any) -> str:
        import subprocess

        lines = []
        lines.append(f"OS: {platform.system()} {platform.release()} ({platform.version()})")
        lines.append(f"Python: {platform.python_version()} ({platform.python_implementation()})")
        lines.append(f"Host: {platform.node()}")
        lines.append(f"Machine: {platform.machine()}")

        total, used, free = shutil.disk_usage(_ROOT)
        lines.append(f"Disk (project drive): {free // (2**30)} GB free / {total // (2**30)} GB total")

        lines.append(f"Project size: {sum(f.stat().st_size for f in _ROOT.rglob('*.py') if f.is_file()) // 1024} KB (.py files)")

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, cwd=_ROOT, timeout=5,
            )
            if result.returncode == 0:
                lines.append(f"Git commit: {result.stdout.strip()}")
        except Exception:
            pass

        lines.append(f"Env vars set: GROQ_API_KEY={'yes' if os.getenv('GROQ_API_KEY') else 'no'}, ANTHROPIC_API_KEY={'yes' if os.getenv('ANTHROPIC_API_KEY') else 'no'}, GOOGLE_API_KEY={'yes' if os.getenv('GOOGLE_API_KEY') else 'no'}")

        return "\n".join(lines)
