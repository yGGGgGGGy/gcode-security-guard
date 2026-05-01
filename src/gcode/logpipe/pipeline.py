"""Log ingestion pipeline — collect, classify, detect, store."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .detectors import classify_level, evaluate
from .models import DetectionHit, DetectionRule, LogEntry, LogSource, SourceType
from .sources import SOURCE_FACTORY

DEFAULT_DB = Path.home() / ".gcode" / "logpipe.db"


class LogPipeline:
    """Central log pipeline: sources → ingest → classify → detect → store."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(DEFAULT_DB)
        self._sources: dict[str, FileSource] = {}  # lazy init
        self._ensure_db()

    def _ensure_db(self):
        self.db_path = str(self.db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL,
                path TEXT NOT NULL,
                enabled INTEGER DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                line TEXT NOT NULL,
                level TEXT,
                ingested_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                pattern TEXT NOT NULL,
                label TEXT DEFAULT 'anomaly',
                severity TEXT DEFAULT 'warn',
                enabled INTEGER DEFAULT 1
            )
        """)
        conn.commit()
        conn.close()

    # ─── Sources ───────────────────────────────────────────

    def add_source(self, name: str, typ: str, path: str) -> int:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "INSERT OR REPLACE INTO sources (name, type, path) VALUES (?, ?, ?)",
            (name, typ, path),
        )
        conn.commit()
        conn.close()
        return cur.lastrowid

    def list_sources(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
        cols = [c[0] for c in conn.execute("PRAGMA table_info(sources)")]
        conn.close()
        return [dict(zip(cols, r)) for r in rows]

    def collect(self, source_name: str | None = None) -> dict[str, list[str]]:
        """Collect new lines from one or all sources."""
        conn = sqlite3.connect(self.db_path)
        src_rows = (
            conn.execute("SELECT * FROM sources WHERE name = ? AND enabled = 1", (source_name,)).fetchall()
            if source_name
            else conn.execute("SELECT * FROM sources WHERE enabled = 1").fetchall()
        )
        cols = [c[0] for c in conn.execute("PRAGMA table_info(sources)")]
        conn.close()

        result: dict[str, list[str]] = {}
        for row in src_rows:
            src = dict(zip(cols, row))
            handler = self._get_source(src)
            if handler is None:
                continue
            lines = handler.read_lines()
            for line in lines:
                self._ingest(src["name"], line)
            result[src["name"]] = lines
        return result

    def _get_source(self, src: dict):
        key = src["name"]
        if key not in self._sources:
            typ = SourceType(src["type"])
            factory = SOURCE_FACTORY.get(typ)
            if factory is None:
                return None
            self._sources[key] = factory(src["path"])
        return self._sources[key]

    def _ingest(self, source_name: str, line: str) -> None:
        level = classify_level(line)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO entries (source_name, line, level, ingested_at) VALUES (?, ?, ?, ?)",
            (source_name, line, level, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    # ─── Entries ───────────────────────────────────────────

    def recent_entries(self, limit: int = 50, level: str | None = None) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        if level:
            rows = conn.execute(
                "SELECT * FROM entries WHERE level = ? ORDER BY ingested_at DESC LIMIT ?",
                (level.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM entries ORDER BY ingested_at DESC LIMIT ?", (limit,)
            ).fetchall()
        cols = [c[0] for c in conn.execute("PRAGMA table_info(entries)")]
        conn.close()
        return [dict(zip(cols, r)) for r in rows]

    # ─── Detection rules ──────────────────────────────────

    def add_rule(self, name: str, pattern: str, label: str = "anomaly", severity: str = "warn") -> int:
        re.compile(pattern)  # validate
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "INSERT OR REPLACE INTO rules (name, pattern, label, severity) VALUES (?, ?, ?, ?)",
            (name, pattern, label, severity),
        )
        conn.commit()
        conn.close()
        return cur.lastrowid

    def list_rules(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT * FROM rules ORDER BY id").fetchall()
        cols = [c[0] for c in conn.execute("PRAGMA table_info(rules)")]
        conn.close()
        return [dict(zip(cols, r)) for r in rows]

    def scan(self, limit: int = 200) -> list[DetectionHit]:
        """Scan recent entries against all enabled detection rules."""
        rules = self.list_rules()
        entries = self.recent_entries(limit)
        hits: list[DetectionHit] = []

        for rule_dict in rules:
            if not rule_dict["enabled"]:
                continue
            rule = DetectionRule(
                name=rule_dict["name"],
                pattern=rule_dict["pattern"],
                label=rule_dict.get("label", "anomaly"),
                severity=rule_dict["severity"],
            )
            for entry_dict in entries:
                entry = LogEntry(
                    source_name=entry_dict["source_name"],
                    line=entry_dict["line"],
                    level=entry_dict.get("level"),
                )
                hits.extend(evaluate(entry, [rule]))

        return hits
