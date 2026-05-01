"""Alert data models — rules, events, notifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class AlertStatus(Enum):
    FIRING = "firing"
    RESOLVED = "resolved"


class NotifyChannel(Enum):
    STDOUT = "stdout"
    WEBHOOK = "webhook"


@dataclass
class AlertRule:
    name: str
    monitor_name: str
    condition: str          # fail, warn, always, consecutive_fail:N
    cooldown_min: int = 5
    enabled: bool = True


@dataclass
class AlertEvent:
    rule_name: str
    monitor_name: str
    status: AlertStatus
    message: str = ""
    fired_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: str | None = None


@dataclass
class Notifier:
    channel: NotifyChannel
    target: str = ""        # webhook URL for webhook channel
    enabled: bool = True
