"""Health check primitives -- HTTP, TCP, process, disk, memory."""

import socket
import subprocess
import time
from dataclasses import dataclass, field

import requests


@dataclass
class CheckResult:
    name: str
    status: str          # "ok", "warn", "fail"
    latency_ms: float
    message: str
    timestamp: float = field(default_factory=time.time)


class Checker:
    """Registry of health check functions."""

    @staticmethod
    def http(url: str, timeout: int = 5, expect_status: int = 200) -> CheckResult:
        start = time.time()
        try:
            resp = requests.get(url, timeout=timeout)
            latency = (time.time() - start) * 1000
            if resp.status_code == expect_status:
                return CheckResult(url, "ok", latency, f"HTTP {resp.status_code}")
            return CheckResult(url, "warn", latency,
                               f"HTTP {resp.status_code} (expected {expect_status})")
        except requests.RequestException as e:
            latency = (time.time() - start) * 1000
            return CheckResult(url, "fail", latency, str(e))

    @staticmethod
    def tcp(host: str, port: int, timeout: int = 5) -> CheckResult:
        start = time.time()
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            latency = (time.time() - start) * 1000
            return CheckResult(f"{host}:{port}", "ok", latency, "TCP reachable")
        except OSError as e:
            latency = (time.time() - start) * 1000
            return CheckResult(f"{host}:{port}", "fail", latency, str(e))

    @staticmethod
    def process(name: str) -> CheckResult:
        start = time.time()
        try:
            result = subprocess.run(
                ["pgrep", "-x", name], capture_output=True, text=True, timeout=5
            )
            latency = (time.time() - start) * 1000
            if result.returncode == 0:
                pids = result.stdout.strip().split()
                return CheckResult(name, "ok", latency, f"Running (PIDs: {','.join(pids)})")
            return CheckResult(name, "fail", latency, "Not running")
        except subprocess.TimeoutExpired:
            return CheckResult(name, "fail", 5000, "pgrep timed out")

    @staticmethod
    def disk(path: str, warn_pct: int = 80, crit_pct: int = 95) -> CheckResult:
        start = time.time()
        try:
            result = subprocess.run(
                ["df", "-h", path], capture_output=True, text=True, timeout=5
            )
            latency = (time.time() - start) * 1000
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                use_pct = int(parts[4].rstrip("%"))
                if use_pct >= crit_pct:
                    return CheckResult(path, "fail", latency, f"Disk {use_pct}% used")
                if use_pct >= warn_pct:
                    return CheckResult(path, "warn", latency, f"Disk {use_pct}% used")
                return CheckResult(path, "ok", latency, f"Disk {use_pct}% used")
            return CheckResult(path, "fail", latency, "df parse error")
        except subprocess.TimeoutExpired:
            return CheckResult(path, "fail", 5000, "df timed out")

    @staticmethod
    def memory(warn_pct: int = 80, crit_pct: int = 95) -> CheckResult:
        start = time.time()
        try:
            result = subprocess.run(
                ["free"], capture_output=True, text=True, timeout=5
            )
            latency = (time.time() - start) * 1000
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                total = int(parts[1])
                used = int(parts[2])
                use_pct = int(used / total * 100)
                if use_pct >= crit_pct:
                    return CheckResult("memory", "fail", latency, f"Memory {use_pct}% used")
                if use_pct >= warn_pct:
                    return CheckResult("memory", "warn", latency, f"Memory {use_pct}% used")
                return CheckResult("memory", "ok", latency, f"Memory {use_pct}% used")
            return CheckResult("memory", "fail", latency, "free parse error")
        except subprocess.TimeoutExpired:
            return CheckResult("memory", "fail", 5000, "free timed out")
