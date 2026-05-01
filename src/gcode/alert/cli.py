"""Alert CLI commands."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from .manager import AlertManager
from .models import AlertRule

console = Console()


@click.group(name="alert")
def alert() -> None:
    """Alert rules and notification management."""


@alert.command()
@click.option("--name", required=True, help="Rule name")
@click.option("--monitor", required=True, help="Monitor target name")
@click.option("--condition", required=True,
              type=click.Choice(["fail", "warn", "always"]),
              help="Trigger condition")
@click.option("--cooldown", default=5, type=int, help="Cooldown in minutes")
def add_rule(name: str, monitor: str, condition: str, cooldown: int) -> None:
    """Add an alert rule."""
    mgr = AlertManager()
    rule = AlertRule(name=name, monitor_name=monitor, condition=condition, cooldown_min=cooldown)
    rid = mgr.add_rule(rule)
    console.print(f"[green]Alert rule added[/] id={rid} name='{name}' monitor='{monitor}'")


@alert.command()
def list_rules() -> None:
    """List alert rules."""
    mgr = AlertManager()
    rules = mgr.list_rules()
    if not rules:
        console.print("[dim]No alert rules configured[/]")
        return
    table = Table(title="Alert Rules")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Monitor")
    table.add_column("Condition")
    table.add_column("Cooldown(min)")
    table.add_column("Enabled")
    for r in rules:
        table.add_row(
            str(r["id"]), r["name"], r["monitor_name"], r["condition"],
            str(r["cooldown_min"]), "Y" if r["enabled"] else "N",
        )
    console.print(table)


@alert.command()
@click.option("--limit", default=20, type=int, help="Number of events to show")
def events(limit: int) -> None:
    """View alert event history."""
    mgr = AlertManager()
    evts = mgr.list_events(limit)
    if not evts:
        console.print("[dim]No alert events yet[/]")
        return
    table = Table(title="Alert Events")
    table.add_column("ID")
    table.add_column("Rule")
    table.add_column("Monitor")
    table.add_column("Status")
    table.add_column("Message")
    table.add_column("Fired At")
    for e in evts:
        style = "red" if e["status"] == "firing" else "green"
        table.add_row(
            str(e["id"]), e["rule_name"], e["monitor_name"],
            f"[{style}]{e['status']}[/]",
            (e["message"] or "")[:60], e["fired_at"] or "-",
        )
    console.print(table)


@alert.command()
@click.option("--channel", required=True,
              type=click.Choice(["stdout", "webhook"]),
              help="Notification channel")
@click.option("--target", default="", help="Channel target (e.g. webhook URL)")
def add_notifier(channel: str, target: str) -> None:
    """Add a notification channel."""
    mgr = AlertManager()
    nid = mgr.add_notifier(channel, target)
    console.print(f"[green]Notifier added[/] id={nid} channel='{channel}'")
