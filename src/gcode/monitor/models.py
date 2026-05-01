"""Monitor data models — check targets, results, thresholds."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class CheckType(enum.Enum):
    HTTP = "http"
    TCP = "tcp"
    PROCESS = "process"


class CheckStatus(enum.Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class MetricKind(enum.Enum):
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    UPTIME = "uptime"


@dataclass
class MonitorTarget:
    name: str
    check_type: CheckType
    address: str
    port: int = 0
    interval_seconds: int = 30
    timeout_seconds: int = 5


@dataclass
class CheckResult:
    check_name: str
    check_type: CheckType
    target: str
    status: CheckStatus
    latency_ms: float | None = None
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class MetricSnapshot:
    target: str
    kind: MetricKind
    value: float
    unit: str = "%"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ThresholdRule:
    name: str
    metric: MetricKind
    warn_pct: float
    fail_pct: float
    target: str = ""
