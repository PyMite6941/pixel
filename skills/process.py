import subprocess
from typing import Any

from skills.base_skill import BaseSkill


class Process(BaseSkill):
    @property
    def name(self) -> str:
        return "process"

    @property
    def description(self) -> str:
        return "List, kill, or start processes on the system"

    @property
    def auto_triggers(self) -> list[str]:
        return ["process", "running", "task manager", "kill", "start process", "list processes"]

    def execute(self, action: str = "list", name: str | None = None, pid: int | None = None, command: str | None = None, **kwargs: Any) -> str:
        if action == "list":
            return self._list_processes(name)
        elif action == "kill":
            return self._kill_process(name, pid)
        elif action == "start":
            if command is None:
                return "Missing 'command' parameter for start action"
            return self._start_process(command)
        return f"Unknown action: {action}. Use: list, kill, start"

    def _list_processes(self, filter_name: str | None = None) -> str:
        try:
            cmd = "Get-Process | Select-Object Name, Id, CPU, WorkingSet64 | ConvertTo-Json"
            result = subprocess.run(
                ["powershell", "-Command", cmd],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return f"Failed to list processes: {result.stderr.strip()}"
            import json
            procs = json.loads(result.stdout)
            if not isinstance(procs, list):
                procs = [procs]
            if filter_name:
                procs = [p for p in procs if filter_name.lower() in p.get("Name", "").lower()]
            procs = sorted(procs, key=lambda p: p.get("WorkingSet64", 0), reverse=True)[:30]
            lines = [f"{'PID':>6} {'CPU%':>5} {'MB':>8}  Name"]
            for p in procs:
                name = p.get("Name", "?")
                pid = p.get("Id", 0)
                cpu = p.get("CPU") or 0
                mb = (p.get("WorkingSet64") or 0) // (1024 * 1024)
                lines.append(f"{pid:>6} {cpu:>5.1f} {mb:>8}  {name}")
            return "\n".join(lines)
        except Exception as e:
            return f"Failed to list processes: {e}"

    def _kill_process(self, name: str | None, pid: int | None) -> str:
        if pid:
            target = f"-Id {pid}"
            label = f"PID {pid}"
        elif name:
            target = f"-Name '{name}'"
            label = f"'{name}'"
        else:
            return "Specify 'name' or 'pid' to kill"
        try:
            result = subprocess.run(
                ["powershell", "-Command", f"Stop-Process {target} -Force"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return f"Killed process {label}"
            return f"Failed to kill {label}: {result.stderr.strip()}"
        except Exception as e:
            return f"Kill failed: {e}"

    def _start_process(self, command: str) -> str:
        try:
            subprocess.Popen(command, shell=True)
            return f"Started: {command}"
        except Exception as e:
            return f"Failed to start process: {e}"
