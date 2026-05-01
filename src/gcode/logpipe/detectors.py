"""Pattern-based anomaly detection rules."""

from __future__ import annotations

import re

from .models import DetectionHit, DetectionRule, LogEntry, Severity


def evaluate(entry: LogEntry, rules: list[DetectionRule]) -> list[DetectionHit]:
    """Evaluate all rules against a single log entry. Returns matching hits."""
    hits: list[DetectionHit] = []
    for rule in rules:
        if not rule.enabled:
            continue
        try:
            if re.search(rule.pattern, entry.line):
                hits.append(DetectionHit(
                    rule=rule.name,
                    severity=rule.severity,
                    label=rule.label,
                    source=entry.source_name,
                    line=entry.line[:200],
                ))
        except re.error:
            continue
    return hits


def classify_level(line: str) -> str | None:
    """Heuristic level classification from log line text."""
    upper = line.upper()
    for lv in ("CRITICAL", "FATAL", "EMERGENCY"):
        if lv in upper:
            return Severity.ERROR.value.upper()
    for lv in ("ERROR", "ERR", "SEVERE"):
        if lv in upper:
            return Severity.ERROR.value.upper()
    for lv in ("WARN", "WARNING"):
        if lv in upper:
            return Severity.WARN.value.upper()
    if "INFO" in upper:
        return Severity.INFO.value.upper()
    if "DEBUG" in upper:
        return "DEBUG"
    return None
