"""Metric collector — system metrics via psutil with /proc fallback."""

from __future__ import annotations

import shutil
from typing import Any

from .models import MetricKind, MetricSnapshot


def _cpu_pct() -> float:
    try:
        import psutil
        return psutil.cpu_percent(interval=1)
    except ImportError:
        return _cpu_pct_fallback()


def _cpu_pct_fallback() -> float:
    with open("/proc/stat") as f:
        fields = f.readline().split()
    idle = int(fields[4])
    total = sum(int(v) for v in fields[1:])
    return round(100.0 * (1.0 - idle / total) if total else 0, 1)


def _mem_pct() -> float:
    try:
        import psutil
        return round(psutil.virtual_memory().percent, 1)
    except ImportError:
        return _mem_pct_fallback()


def _mem_pct_fallback() -> float:
    with open("/proc/meminfo") as f:
        lines = f.readlines()
    mem: dict[str, int] = {}
    for line in lines:
        key = line.split(":")[0]
        val = line.split(":")[1].strip().split()[0]
        mem[key] = int(val)
    used = mem["MemTotal"] - mem["MemAvailable"]
    return round(100.0 * used / mem["MemTotal"], 1)


def _disk_pct(target: str = "") -> float:
    try:
        import psutil
        path = target or "/"
        return round(psutil.disk_usage(path).percent, 1)
    except ImportError:
        return _disk_pct_fallback(target)


def _disk_pct_fallback(target: str = "") -> float:
    path = target or "/"
    usage = shutil.disk_usage(path)
    return round(100.0 * usage.used / usage.total, 1)


_COLLECTOR_MAP: dict[MetricKind, Any] = {
    MetricKind.CPU: _cpu_pct,
    MetricKind.MEMORY: _mem_pct,
    MetricKind.DISK: _disk_pct,
}


def collect(target: str, kind: MetricKind) -> MetricSnapshot:
    fn = _COLLECTOR_MAP.get(kind)
    if fn is None:
        raise ValueError(f"Unsupported metric kind: {kind}")
    if kind == MetricKind.DISK:
        value = fn(target)
    else:
        value = fn()
    return MetricSnapshot(target=target, kind=kind, value=value, unit="%")
