"""Log pipeline data models — sources, entries, detection rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SourceType(Enum):
    FILE = "file"


class Severity(Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass
class LogSource:
    name: str
    type: SourceType
    path: str
    enabled: bool = True


@dataclass
class LogEntry:
    source_name: str
    line: str
    level: str | None = None         # auto-detected: ERROR, WARN, INFO
    parsed_fields: dict | None = None
    ingested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DetectionRule:
    name: str
    pattern: str                     # regex
    label: str = "anomaly"
    severity: Severity = Severity.WARN
    enabled: bool = True


@dataclass
class DetectionHit:
    rule: str
    severity: Severity
    label: str
    source: str
    line: str
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
