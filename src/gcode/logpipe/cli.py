"""Log pipeline CLI commands."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from .pipeline import LogPipeline

console = Console()


@click.group(name="logpipe")
def logpipe() -> None:
    """Log collection, aggregation, and anomaly detection."""


@logpipe.command()
@click.option("--name", required=True, help="Source name")
@click.option("--type", "typ", required=True, type=click.Choice(["file"]), help="Source type")
@click.option("--path", required=True, help="File path")
def add_source(name: str, typ: str, path: str) -> None:
    """Add a log source."""
    pipe = LogPipeline()
    sid = pipe.add_source(name, typ, path)
    console.print(f"[green]Log source added[/] id={sid} name='{name}' type={typ} path='{path}'")


@logpipe.command()
def list_sources() -> None:
    """List log sources."""
    pipe = LogPipeline()
    sources = pipe.list_sources()
    if not sources:
        console.print("[dim]No log sources configured[/]")
        return
    table = Table(title="Log Sources")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Path")
    table.add_column("Enabled")
    for s in sources:
        table.add_row(str(s["id"]), s["name"], s["type"], s["path"], "Y" if s["enabled"] else "N")
    console.print(table)


@logpipe.command()
@click.option("--name", help="Source name (omit for all)")
def collect(name: str | None) -> None:
    """Collect new log lines from sources."""
    pipe = LogPipeline()
    results = pipe.collect(name)
    total = sum(len(v) for v in results.values())
    console.print(f"[green]Collected {total} lines from {len(results)} source(s)[/]")


@logpipe.command()
@click.option("--level", help="Filter by level (ERROR, WARN, INFO)")
@click.option("--limit", default=30, type=int, help="Number of entries")
def entries(level: str | None, limit: int) -> None:
    """View recent log entries."""
    pipe = LogPipeline()
    rows = pipe.recent_entries(limit, level)
    if not rows:
        console.print("[dim]No log entries[/]")
        return
    table = Table(title="Log Entries")
    table.add_column("Time")
    table.add_column("Source")
    table.add_column("Level")
    table.add_column("Line")
    for r in rows:
        lvl = r["level"] or "-"
        lvl_style = "red" if lvl in ("ERROR", "CRITICAL") else ("yellow" if lvl == "WARN" else "dim")
        table.add_row(
            r["ingested_at"] or "-",
            r["source_name"],
            f"[{lvl_style}]{lvl}[/]",
            (r["line"] or "")[:100],
        )
    console.print(table)


@logpipe.command()
@click.option("--name", required=True, help="Rule name")
@click.option("--pattern", required=True, help="Regex pattern")
@click.option("--label", default="anomaly", help="Hit label")
@click.option("--severity", type=click.Choice(["info", "warn", "error"]), default="warn", help="Severity")
def add_rule(name: str, pattern: str, label: str, severity: str) -> None:
    """Add a detection rule."""
    pipe = LogPipeline()
    try:
        rid = pipe.add_rule(name, pattern, label, severity)
        console.print(f"[green]Detection rule added[/] id={rid} name='{name}'")
    except re.error as e:
        console.print(f"[red]Invalid regex: {e}[/]")


@logpipe.command()
@click.option("--limit", default=200, type=int, help="Entries to scan")
def scan(limit: int) -> None:
    """Scan recent logs for anomalies."""
    pipe = LogPipeline()
    hits = pipe.scan(limit)
    if not hits:
        console.print("[dim]No anomalies detected[/]")
        return
    table = Table(title="Anomaly Detection")
    table.add_column("Rule")
    table.add_column("Severity")
    table.add_column("Source")
    table.add_column("Line")
    for h in hits:
        sev = h.severity.value
        sev_style = "red" if sev == "error" else ("yellow" if sev == "warn" else "dim")
        table.add_row(h.rule, f"[{sev_style}]{sev}[/]", h.source, h.line[:100])
    console.print(table)
