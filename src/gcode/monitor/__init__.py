"""Service monitoring engine — health checks, metrics collection."""

from rich.console import Console
from rich.table import Table

from gcode.monitor.evaluator import Evaluator

console = Console()


def _fire_alerts_for_failures(result) -> None:
    """Fire alerts for any failed or warned checks."""
    from gcode.alert.engine import AlertEngine, Severity

    engine = AlertEngine()
    for r in result.results:
        if r.status == "fail":
            engine.fire(
                title=f"Health check failed: {r.name}",
                severity=Severity.CRITICAL,
                source=f"monitor:{r.name}",
                message=r.message,
            )
        elif r.status == "warn":
            engine.fire(
                title=f"Health check warning: {r.name}",
                severity=Severity.WARN,
                source=f"monitor:{r.name}",
                message=r.message,
            )


def register_commands(cli_group):
    """Register monitor commands to the CLI."""

    @cli_group.command()
    def check():
        """Run health checks against all configured targets."""
        config = Evaluator.default_checks()
        result = Evaluator.run_checks(config)

        table = Table(title="Health Check Results")
        table.add_column("Check", style="cyan")
        table.add_column("Status")
        table.add_column("Latency")
        table.add_column("Message")

        for r in result.results:
            style = {"ok": "green", "warn": "yellow", "fail": "red"}[r.status]
            table.add_row(r.name, f"[{style}]{r.status}[/{style}]",
                          f"{r.latency_ms:.1f}ms", r.message)

        console.print(table)
        console.print(f"OK: {result.ok_count} | WARN: {result.warn_count} | "
                      f"FAIL: {result.fail_count} | Time: {result.duration_ms:.0f}ms")

        if not result.healthy:
            _fire_alerts_for_failures(result)
            console.print("[yellow]Alerts fired for failed checks.[/yellow]")
