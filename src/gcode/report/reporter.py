"""Report generation for daily/weekly/incident summaries."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ReportSection:
    title: str
    content: str


class Reporter:
    """Generates structured ops reports with live data from all modules."""

    def generate(self, report_type: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        header = f"Gcode Report ({report_type.upper()}) — {timestamp}\n{'=' * 60}"

        if report_type == "daily":
            sections = self._daily_sections()
        elif report_type == "weekly":
            sections = self._weekly_sections()
        elif report_type == "incident":
            sections = self._incident_sections()
        else:
            sections = []

        return header + "\n\n" + "\n\n".join(
            f"## {s.title}\n{s.content}" for s in sections
        )

    def _daily_sections(self) -> list[ReportSection]:
        return [
            ReportSection("Service Health", self._monitor_summary()),
            ReportSection("Alerts Fired", self._alert_summary()),
            ReportSection("Log Anomalies", self._logpipe_summary()),
        ]

    def _weekly_sections(self) -> list[ReportSection]:
        return [
            ReportSection("Weekly Summary", self._monitor_summary()),
            ReportSection("Incidents", self._alert_summary()),
            ReportSection("Trends", self._logpipe_summary()),
        ]

    def _incident_sections(self) -> list[ReportSection]:
        return [
            ReportSection("Incident Timeline", self._alert_summary()),
            ReportSection("Root Cause Analysis", self._monitor_summary()),
            ReportSection("Action Items", "Follow-up actions and owners (to be filled)."),
        ]

    @staticmethod
    def _monitor_summary() -> str:
        try:
            from gcode.monitor.evaluator import Evaluator
            config = Evaluator.default_checks()
            result = Evaluator.run_checks(config)
            lines = []
            for r in result.results:
                icon = {"ok": "✓", "warn": "⚠", "fail": "✗"}[r.status]
                lines.append(f"  {icon} {r.name}: {r.message} ({r.latency_ms:.0f}ms)")
            summary = f"OK: {result.ok_count} | WARN: {result.warn_count} | FAIL: {result.fail_count}"
            return "\n".join(lines) + f"\n{summary}"
        except Exception as e:
            return f"(monitor unavailable: {e})"

    @staticmethod
    def _alert_summary() -> str:
        try:
            from gcode.alert.engine import AlertEngine
            engine = AlertEngine()
            active = engine.active()
            if not active:
                return "No active alerts."
            lines = []
            for a in active:
                lines.append(f"  [{a.severity.value}] {a.title} — {a.source}")
            return "\n".join(lines)
        except Exception as e:
            return f"(alert unavailable: {e})"

    @staticmethod
    def _logpipe_summary() -> str:
        try:
            from gcode.logpipe.engine import LogPipeline
            pipeline = LogPipeline()
            anomalies = pipeline.detect_anomalies()
            if not anomalies:
                return "No anomalies detected."
            lines = []
            for a in anomalies:
                lines.append(f"  {a.pattern[:60]} (×{a.count})")
            return "\n".join(lines)
        except Exception as e:
            return f"(logpipe unavailable: {e})"
