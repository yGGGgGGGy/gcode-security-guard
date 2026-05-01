"""Log pipeline engine -- collection, aggregation, anomaly detection."""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class LogEntry:
    timestamp: str
    source: str
    level: str
    message: str
    raw: str = ""


@dataclass
class Anomaly:
    pattern: str
    count: int
    threshold: int
    sample: str


class LogPipeline:
    """Ingests, stores, and analyzes log entries."""

    def __init__(self, storage_path: Path | None = None):
        self.storage = storage_path or Path.home() / ".gcode" / "logs.jsonl"
        self.storage.parent.mkdir(parents=True, exist_ok=True)

    def ingest(self, entry: LogEntry):
        with open(self.storage, "a") as f:
            f.write(json.dumps(entry.__dict__) + "\n")

    def ingest_batch(self, entries: list[LogEntry]):
        with open(self.storage, "a") as f:
            for e in entries:
                f.write(json.dumps(e.__dict__) + "\n")

    def query(self, *, level: str | None = None, source: str | None = None,
              keyword: str | None = None, limit: int = 50) -> list[LogEntry]:
        results = []
        if not self.storage.exists():
            return results

        with open(self.storage) as f:
            for line in f:
                entry = LogEntry(**json.loads(line))
                if level and entry.level.upper() != level.upper():
                    continue
                if source and entry.source != source:
                    continue
                if keyword and keyword.lower() not in entry.message.lower():
                    continue
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def detect_anomalies(self, window_minutes: int = 60,
                         threshold: int = 10) -> list[Anomaly]:
        """Find patterns that occur above threshold in the recent window."""
        entries = self.query(limit=500)
        error_patterns: Counter[str] = Counter()
        samples: dict[str, str] = {}

        for e in entries:
            if e.level.upper() in ("ERROR", "CRITICAL", "FATAL"):
                simplified = re.sub(r'[0-9a-fA-F]{8,}', '<ID>', e.message)
                simplified = re.sub(r'\d+', '<N>', simplified)
                error_patterns[simplified] += 1
                if simplified not in samples:
                    samples[simplified] = e.message

        return [
            Anomaly(pattern=p, count=c, threshold=threshold, sample=samples[p])
            for p, c in error_patterns.most_common()
            if c >= threshold
        ]

    def stats(self) -> dict:
        """Return basic log statistics."""
        if not self.storage.exists():
            return {"total": 0}

        levels: Counter[str] = Counter()
        sources: Counter[str] = Counter()
        total = 0

        with open(self.storage) as f:
            for line in f:
                e = json.loads(line)
                levels[e.get("level", "UNKNOWN")] += 1
                sources[e.get("source", "UNKNOWN")] += 1
                total += 1

        return {
            "total": total,
            "by_level": dict(levels.most_common()),
            "by_source": dict(sources.most_common(10)),
        }
