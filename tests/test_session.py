"""Tests for session manager."""

import tempfile
from pathlib import Path

from gcode.core.session import SessionManager


def test_ask_status():
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "test.db"
        sm = SessionManager(db_path=db)
        resp = sm.ask("check service status")
        assert "nominal" in resp.lower()


def test_ask_alerts():
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "test.db"
        sm = SessionManager(db_path=db)
        resp = sm.ask("are there any alerts?")
        assert "no active alerts" in resp.lower()


def test_ask_logs():
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "test.db"
        sm = SessionManager(db_path=db)
        resp = sm.ask("show me recent error logs")
        assert "anomalous" in resp.lower()
