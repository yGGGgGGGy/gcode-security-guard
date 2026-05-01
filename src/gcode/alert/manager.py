"""Alert rule evaluation, dedup via cooldown, event lifecycle."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import AlertEvent, AlertRule, AlertStatus, Notifier, NotifyChannel
from .notifier import notify

DEFAULT_DB = Path.home() / ".gcode" / "alerts.db"


class AlertManager:
    """Evaluates alert rules, manages cooldown dedup, and dispatches notifications."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(DEFAULT_DB)
        self._ensure_db()

    def _ensure_db(self):
        self.db_path = str(self.db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                monitor_name TEXT NOT NULL,
                condition TEXT NOT NULL,
                cooldown_min INTEGER DEFAULT 5,
                enabled INTEGER DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT NOT NULL,
                monitor_name TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT DEFAULT '',
                fired_at TEXT NOT NULL,
                resolved_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                target TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1
            )
        """)
        conn.commit()
        conn.close()

    def add_rule(self, rule: AlertRule) -> int:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "INSERT OR REPLACE INTO rules (name, monitor_name, condition, cooldown_min, enabled) VALUES (?, ?, ?, ?, ?)",
            (rule.name, rule.monitor_name, rule.condition, rule.cooldown_min, int(rule.enabled)),
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

    def evaluate(self, monitor_name: str, check_status: str, message: str = "") -> AlertEvent | None:
        """Evaluate all matching rules. Returns AlertEvent if firing, None otherwise."""
        conn = sqlite3.connect(self.db_path)
        rule_rows = conn.execute(
            "SELECT * FROM rules WHERE monitor_name = ? AND enabled = 1", (monitor_name,)
        ).fetchall()
        if not rule_rows:
            conn.close()
            return None

        cols = [c[0] for c in conn.execute("PRAGMA table_info(rules)")]
        for row in rule_rows:
            rule = dict(zip(cols, row))
            if self._condition_matches(rule["condition"], check_status, monitor_name, conn):
                if not self._in_cooldown(rule["id"], rule["cooldown_min"], conn):
                    conn.execute(
                        "INSERT INTO events (rule_name, monitor_name, status, message, fired_at) VALUES (?, ?, ?, ?, ?)",
                        (rule["name"], monitor_name, AlertStatus.FIRING.value, message,
                         datetime.now(timezone.utc).isoformat()),
                    )
                    conn.commit()
                    event = AlertEvent(
                        rule_name=rule["name"],
                        monitor_name=monitor_name,
                        status=AlertStatus.FIRING,
                        message=message,
                    )
                    conn.close()
                    return event
        conn.close()
        return None

    def _condition_matches(self, condition: str, check_status: str, monitor_name: str,
                           conn: sqlite3.Connection) -> bool:
        if condition == "fail" and check_status == "fail":
            return True
        if condition == "warn" and check_status in ("warn", "fail"):
            return True
        if condition == "always":
            return True
        if condition.startswith("consecutive_fail:"):
            n = int(condition.split(":")[1])
            rows = conn.execute(
                """SELECT status FROM events
                   WHERE monitor_name = ? AND status = 'firing'
                   ORDER BY fired_at DESC LIMIT ?""",
                (monitor_name, n),
            ).fetchall()
            return len(rows) >= n
        return False

    def _in_cooldown(self, rule_id: int, cooldown_min: int, conn: sqlite3.Connection) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=cooldown_min)).isoformat()
        row = conn.execute(
            "SELECT fired_at FROM events WHERE rule_name = (SELECT name FROM rules WHERE id = ?) AND status = 'firing' ORDER BY fired_at DESC LIMIT 1",
            (rule_id,),
        ).fetchone()
        if row and row[0] >= cutoff:
            return True
        return False

    def list_events(self, limit: int = 20) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT * FROM events ORDER BY fired_at DESC LIMIT ?", (limit,)).fetchall()
        cols = [c[0] for c in conn.execute("PRAGMA table_info(events)")]
        conn.close()
        return [dict(zip(cols, r)) for r in rows]

    def get_events_for_monitor(self, monitor_name: str, limit: int = 10) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT * FROM events WHERE monitor_name = ? ORDER BY fired_at DESC LIMIT ?",
            (monitor_name, limit),
        ).fetchall()
        cols = [c[0] for c in conn.execute("PRAGMA table_info(events)")]
        conn.close()
        return [dict(zip(cols, r)) for r in rows]

    # ─── Notifiers ──────────────────────────────────────────

    def add_notifier(self, channel: str, target: str = "") -> int:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "INSERT INTO notifiers (channel, target) VALUES (?, ?)", (channel, target)
        )
        conn.commit()
        conn.close()
        return cur.lastrowid

    def list_notifiers(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT * FROM notifiers ORDER BY id").fetchall()
        cols = [c[0] for c in conn.execute("PRAGMA table_info(notifiers)")]
        conn.close()
        return [dict(zip(cols, r)) for r in rows]
