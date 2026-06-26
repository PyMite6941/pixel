import subprocess
from typing import Any

from skills.base_skill import BaseSkill


class Network(BaseSkill):
    @property
    def name(self) -> str:
        return "network"

    @property
    def description(self) -> str:
        return "Report network info: IP addresses, connectivity, DNS, ports"

    @property
    def auto_triggers(self) -> list[str]:
        return ["network", "ip address", "my ip", "connectivity", "internet", "dns", "ports", "wifi", "network info"]

    def execute(self, action: str = "info", target: str = "", port: int | None = None, **kwargs: Any) -> str:
        if action == "info":
            return self._network_info()
        elif action == "external_ip":
            return self._external_ip()
        elif action == "ping":
            if not target:
                return "Missing 'target' parameter for ping"
            return self._ping(target)
        elif action == "dns":
            if not target:
                return "Missing 'target' parameter for DNS lookup"
            return self._dns_lookup(target)
        elif action == "connections":
            return self._connections()
        return f"Unknown action: {action}. Use: info, external_ip, ping, dns, connections"

    def _network_info(self) -> str:
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -ne 'Loopback Pseudo-Interface 1'} | "
                 "Select-Object InterfaceAlias, IPAddress, PrefixLength | ConvertTo-Json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return f"Network info failed: {result.stderr.strip()}"
            import json
            adapters = json.loads(result.stdout)
            if not isinstance(adapters, list):
                adapters = [adapters]
            lines = [f"{'Interface':<30} {'IP Address':<16} {'Subnet'}", "-" * 60]
            for a in adapters:
                iface = a.get("InterfaceAlias", "?")[:30]
                ip = a.get("IPAddress", "?")
                prefix = a.get("PrefixLength", "?")
                lines.append(f"{iface:<30} {ip:<16} /{prefix}")
            return "\n".join(lines)
        except Exception as e:
            return f"Network info failed: {e}"

    def _external_ip(self) -> str:
        try:
            import requests
            resp = requests.get("https://api.ipify.org?format=json", timeout=10)
            if resp.status_code == 200:
                return f"External IP: {resp.json().get('ip', 'unknown')}"
            return "Could not determine external IP"
        except Exception as e:
            return f"External IP check failed: {e}"

    def _ping(self, target: str) -> str:
        try:
            result = subprocess.run(
                ["ping", "-n", "4", target],
                capture_output=True, text=True, timeout=15,
            )
            lines = result.stdout.split("\n")[-3:]
            avg = [l for l in lines if "Average" in l or "平均" in l]
            if avg:
                return f"Ping to {target}: {avg[0].strip()}"
            if result.returncode == 0:
                return f"Ping to {target}: reachable"
            return f"Ping to {target}: unreachable"
        except Exception as e:
            return f"Ping failed: {e}"

    def _dns_lookup(self, target: str) -> str:
        try:
            result = subprocess.run(
                ["nslookup", target],
                capture_output=True, text=True, timeout=10,
            )
            lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
            addrs = [l for l in lines if "Address" in l and ":" not in l.split("Address")[0]]
            return "\n".join(addrs[:5]) if addrs else result.stdout.strip()[:1000]
        except Exception as e:
            return f"DNS lookup failed: {e}"

    def _connections(self) -> str:
        try:
            result = subprocess.run(
                ["netstat", "-n"],
                capture_output=True, text=True, timeout=10,
            )
            lines = result.stdout.split("\n")
            conns = [l for l in lines if "ESTABLISHED" in l or "LISTENING" in l or "TIME_WAIT" in l]
            return "\n".join(conns[:30]) if conns else "No active connections found"
        except Exception as e:
            return f"Connection list failed: {e}"
