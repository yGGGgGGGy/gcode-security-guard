"""Service monitoring engine — health checks, metrics collection."""

from rich.console import Console
from rich.table import Table

from gcode.monitor.evaluator import Evaluator

console = Console()


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
