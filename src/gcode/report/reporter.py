"""Report generation for daily/weekly/incident summaries."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ReportSection:
    title: str
    content: str


class Reporter:
    """Generates structured ops reports."""

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
            ReportSection(
                "Service Health",
                "[monitor] Service health summary will appear here.\n"
                "Integrate with monitor module for live data.",
            ),
            ReportSection(
                "Alerts Fired",
                "[alert] Alert summary will appear here.\n"
                "Integrate with alert module for live data.",
            ),
            ReportSection(
                "Log Anomalies",
                "[logpipe] Log anomaly summary will appear here.\n"
                "Integrate with logpipe module for live data.",
            ),
        ]

    def _weekly_sections(self) -> list[ReportSection]:
        return [
            ReportSection("Weekly Summary", "Aggregated ops metrics for the week."),
            ReportSection(
                "Incidents", "List of incidents and their resolution status."
            ),
            ReportSection(
                "Trends", "Week-over-week comparisons and anomaly trends."
            ),
        ]

    def _incident_sections(self) -> list[ReportSection]:
        return [
            ReportSection(
                "Incident Timeline",
                "Chronological log of events during the incident.",
            ),
            ReportSection(
                "Root Cause Analysis",
                "Analysis of the root cause to be filled in.",
            ),
            ReportSection(
                "Action Items",
                "Follow-up actions and owners.",
            ),
        ]
