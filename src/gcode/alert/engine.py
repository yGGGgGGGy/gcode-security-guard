"""Alert engine -- threshold evaluation, routing, escalation."""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


@dataclass
class Alert:
    id: str
    title: str
    severity: Severity
    source: str
    message: str
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False
    resolved: bool = False


class AlertEngine:
    """Creates, routes, and manages alerts."""

    def __init__(self, storage_path: Path | None = None):
        self.storage = storage_path or Path.home() / ".gcode" / "alerts.json"
        self.storage.parent.mkdir(parents=True, exist_ok=True)
        self._alerts: list[Alert] = self._load()

    def fire(self, title: str, severity: Severity, source: str,
             message: str) -> Alert:
        alert = Alert(
            id=f"ALERT-{int(time.time())}-{hash(title) & 0xFFFF:04x}",
            title=title,
            severity=severity,
            source=source,
            message=message,
        )
        self._alerts.append(alert)
        self._save()
        return alert

    def ack(self, alert_id: str) -> bool:
        for a in self._alerts:
            if a.id == alert_id:
                a.acknowledged = True
                self._save()
                return True
        return False

    def resolve(self, alert_id: str) -> bool:
        for a in self._alerts:
            if a.id == alert_id:
                a.resolved = True
                self._save()
                return True
        return False

    def active(self) -> list[Alert]:
        return [a for a in self._alerts if not a.resolved]

    def summary(self) -> dict:
        active = self.active()
        return {
            "total_fired": len(self._alerts),
            "active": len(active),
            "by_severity": {
                s.value: len([a for a in active if a.severity == s])
                for s in Severity
            },
        }

    def _load(self) -> list[Alert]:
        if not self.storage.exists():
            return []
        with open(self.storage) as f:
            data = json.load(f)
        alerts = []
        for item in data:
            if isinstance(item.get("severity"), str):
                item["severity"] = Severity(item["severity"])
            alerts.append(Alert(**item))
        return alerts

    def _save(self):
        with open(self.storage, "w") as f:
            json.dump([a.__dict__ for a in self._alerts], f, indent=2)
