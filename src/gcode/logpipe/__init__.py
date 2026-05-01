"""Log pipeline engine -- collection, aggregation, anomaly detection."""

import click
from rich.console import Console
from rich.table import Table

from gcode.logpipe.engine import LogPipeline, LogEntry

console = Console()
pipeline = LogPipeline()


def register_commands(cli_group):
    """Register logpipe commands to the CLI."""

    @cli_group.group()
    def log():
        """Manage and query logs."""
        pass

    @log.command()
    @click.option("--level", "-l", default=None, help="Filter by log level")
    @click.option("--source", "-s", default=None, help="Filter by source")
    @click.option("--keyword", "-k", default=None, help="Search keyword")
    @click.option("--limit", "-n", default=50, help="Max entries")
    def query(level, source, keyword, limit):
        """Query log entries."""
        entries = pipeline.query(
            level=level, source=source, keyword=keyword, limit=limit
        )
        if not entries:
            console.print("[dim]No matching log entries.[/dim]")
            return

        for e in entries:
            level_color = {"ERROR": "red", "WARN": "yellow", "INFO": "green",
                           "DEBUG": "dim"}.get(e.level.upper(), "white")
            console.print(
                f"[dim]{e.timestamp[:19]}[/dim] "
                f"[{level_color}]{e.level}[/{level_color}] "
                f"[cyan]{e.source}[/cyan] {e.message[:120]}"
            )

    @log.command()
    def stats():
        """Show log statistics."""
        s = pipeline.stats()
        console.print(f"[bold]Total entries:[/bold] {s['total']}")

        if s.get("by_level"):
            console.print("\n[bold]By Level:[/bold]")
            for level, count in s["by_level"].items():
                console.print(f"  {level}: {count}")

        if s.get("by_source"):
            console.print("\n[bold]By Source:[/bold]")
            for source, count in s["by_source"].items():
                console.print(f"  {source}: {count}")

    @log.command()
    @click.option("--threshold", "-t", default=10, help="Min occurrences for anomaly")
    def anomalies(threshold):
        """Detect anomalous log patterns."""
        results = pipeline.detect_anomalies(threshold=threshold)
        if not results:
            console.print("[green]No anomalies detected.[/green]")
            return

        table = Table(title="Log Anomalies")
        table.add_column("Pattern", style="cyan", max_width=60)
        table.add_column("Count", justify="right")
        for a in results:
            table.add_row(a.pattern[:60], str(a.count))
        console.print(table)
