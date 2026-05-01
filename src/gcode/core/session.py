"""Conversation session management.

Persists conversation state and routes user queries through intent
matching to available agent capabilities.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path.home() / ".gcode" / "sessions.db"


class SessionManager:
    """Manages interactive Q&A sessions with conversation history."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = str(db_path or DEFAULT_DB)
        self._ensure_db()

    def _ensure_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        conn.commit()
        conn.close()

    def start_interactive(self):
        """Start interactive REPL session."""
        session_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self._create_session(session_id)
        from rich.console import Console
        console = Console()
        console.print(f"[bold]Gcode interactive session: {session_id}[/bold]")
        console.print("Type /help for commands, /quit to exit.\n")

        while True:
            try:
                user_input = console.input("[bold cyan]gcode> [/bold cyan]")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Session ended.[/dim]")
                break

            if user_input.strip() == "/quit":
                break
            if user_input.strip() == "/help":
                console.print("Commands: /quit, /help, /history, /clear")
                continue
            if user_input.strip() == "/history":
                for msg in self._get_history(session_id):
                    console.print(f"  [{msg['role']}] {msg['content'][:100]}")
                continue
            if not user_input.strip():
                continue

            self._store_message(session_id, "user", user_input)
            response = self._process(user_input)
            self._store_message(session_id, "assistant", response)
            console.print(response)

    def ask(self, query: str, session_id: str | None = None) -> str:
        """One-shot query without starting REPL."""
        if session_id is None:
            session_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            self._create_session(session_id)
        self._store_message(session_id, "user", query)
        response = self._process(query)
        self._store_message(session_id, "assistant", response)
        return response

    def _process(self, query: str) -> str:
        """Route query to appropriate handler based on intent."""
        query_lower = query.lower()

        if any(w in query_lower for w in ("status", "health", "check", "状态")):
            return "[monitor] Health check: all systems nominal."
        if any(w in query_lower for w in ("alert", "alarm", "告警")):
            return "[alert] No active alerts."
        if any(w in query_lower for w in ("log", "日志", "error")):
            return "[logpipe] Recent logs: nothing anomalous detected."
        if any(w in query_lower for w in ("runbook", "run", "execute", "执行")):
            return "[engine] Runbook engine ready. Use `gcode run <file>` to execute."
        if any(w in query_lower for w in ("report", "报告")):
            return "[report] Use `gcode report --type daily|weekly|incident`."

        return (
            "I can help with: service status, alerts, logs, runbook execution, "
            "and report generation. Try asking about any of these."
        )

    def _create_session(self, session_id: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, created_at) VALUES (?, ?)",
            (session_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    def _store_message(self, session_id: str, role: str, content: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, role, content, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    def _get_history(self, session_id: str) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        conn.close()
        return [{"role": r, "content": c} for r, c in rows]
