"""Alert notification engine -- threshold alerts, routing, escalation."""

import click
from rich.console import Console
from rich.table import Table

from gcode.alert.engine import AlertEngine, Severity

console = Console()
engine = AlertEngine()


def register_commands(cli_group):
    """Register alert commands to the CLI."""

    @cli_group.group()
    def alert():
        """Manage alerts."""
        pass

    @alert.command()
    def list():
        """List active alerts."""
        active = engine.active()
        if not active:
            console.print("[green]No active alerts.[/green]")
            return

        table = Table(title="Active Alerts")
        table.add_column("ID", style="cyan")
        table.add_column("Severity")
        table.add_column("Title")
        table.add_column("Source")
        table.add_column("Acknowledged")

        for a in active:
            sev_style = {"info": "blue", "warn": "yellow", "critical": "red"}
            table.add_row(a.id, f"[{sev_style[a.severity.value]}]{a.severity.value}[/]",
                          a.title, a.source, str(a.acknowledged))

        console.print(table)

    @alert.command()
    @click.argument("alert_id")
    def ack(alert_id):
        """Acknowledge an alert."""
        if engine.ack(alert_id):
            console.print(f"[green]Alert {alert_id} acknowledged.[/green]")
        else:
            console.print(f"[red]Alert {alert_id} not found.[/red]")

    @alert.command()
    @click.argument("alert_id")
    def resolve(alert_id):
        """Resolve an alert."""
        if engine.resolve(alert_id):
            console.print(f"[green]Alert {alert_id} resolved.[/green]")
        else:
            console.print(f"[red]Alert {alert_id} not found.[/red]")

    @alert.command()
    def summary():
        """Show alert summary."""
        s = engine.summary()
        console.print(f"Total fired: {s['total_fired']}")
        console.print(f"Active: {s['active']}")
        for sev, count in s["by_severity"].items():
            console.print(f"  {sev}: {count}")
