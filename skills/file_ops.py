import os
from pathlib import Path
from typing import Any

from skills.base_skill import BaseSkill

_BLOCKED_DIRS = [
    "C:\\Windows\\System32",
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    os.path.expandvars("%SystemRoot%"),
]
_BLOCKED_FILE_EXTS = {".exe", ".dll", ".sys", ".bat", ".ps1", ".vbs", ".scr", ".ocx", ".drv"}
_MAX_FILE_SIZE = 10 * 1024 * 1024


class FileOps(BaseSkill):
    @property
    def name(self) -> str:
        return "file_ops"

    @property
    def description(self) -> str:
        return "Read, write, list, copy, move, delete files anywhere on the filesystem (with safety checks)"

    @property
    def auto_triggers(self) -> list[str]:
        return ["read file", "write file", "list files", "show file", "open file", "what files", "file content", "create file", "delete file", "copy file", "move file"]

    def _resolve(self, path: str) -> Path:
        return Path(path).resolve()

    def _check_safe(self, target: Path) -> None:
        resolved = target.resolve()
        for blocked in _BLOCKED_DIRS:
            b = Path(blocked).resolve()
            if str(resolved).lower().startswith(str(b).lower()):
                raise PermissionError(f"Access denied: path is inside a protected system directory ({blocked})")

    def execute(self, action: str = "read", path: str = ".", content: str | None = None, new_path: str | None = None, pattern: str = "*", **kwargs: Any) -> str:
        target = self._resolve(path)

        if action in ("read", "write", "delete", "exists"):
            self._check_safe(target)

        if action == "read":
            if not target.exists():
                return f"File not found: {target}"
            if not target.is_file():
                return f"Not a file: {target}"
            size = target.stat().st_size
            if size > _MAX_FILE_SIZE:
                return f"File too large: {size // (1024*1024)} MB (max {_MAX_FILE_SIZE // (1024*1024)} MB)"
            try:
                return target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return f"Binary file ({size} bytes). Use shell skill to handle binary files."

        if action == "write":
            if content is None:
                return "Missing 'content' parameter for write action"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Written {len(content)} bytes to {target}"

        if action == "list":
            search_path = self._resolve(path)
            if not search_path.exists():
                return f"Path not found: {search_path}"
            if not search_path.is_dir():
                return f"Not a directory: {search_path}"
            files = sorted(search_path.iterdir())
            dirs = [f for f in files if f.is_dir()]
            files_only = [f for f in files if f.is_file()]
            lines = []
            for d in dirs:
                lines.append(f"[DIR]  {d.name}/")
            for f in files_only:
                size = f.stat().st_size
                lines.append(f"[FILE] {f.name} ({size} bytes)")
            return "\n".join(lines) if lines else f"Empty directory: {search_path}"

        if action == "delete":
            if not target.exists():
                return f"Not found: {target}"
            if target.is_dir():
                target.rmdir()
                return f"Deleted directory: {target}"
            target.unlink()
            return f"Deleted file: {target}"

        if action == "exists":
            if target.exists():
                size = target.stat().st_size if target.is_file() else 0
                kind = "directory" if target.is_dir() else "file"
                return f"Exists: {target} ({kind}, {size} bytes)"
            return f"Not found: {target}"

        if action in ("copy", "move"):
            if not new_path:
                return f"Missing 'new_path' parameter for {action} action"
            if not target.exists():
                return f"Source not found: {target}"
            dest = self._resolve(new_path)
            self._check_safe(dest)
            if action == "copy":
                if target.is_dir():
                    import shutil
                    shutil.copytree(target, dest)
                    return f"Copied directory {target} to {dest}"
                import shutil
                shutil.copy2(target, dest)
                return f"Copied file {target} to {dest}"
            else:
                target.rename(dest)
                return f"Moved {target} to {dest}"

        return f"Unknown action: {action}. Use: read, write, list, delete, exists, copy, move"
