"""CLI entry point for Gcode ops agent."""

import click
from rich.console import Console

from gcode.core.engine import RunbookEngine
from gcode.core.session import SessionManager

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="gcode")
def main():
    """Gcode - AI-powered ops agent for monitoring, alerting, and automation."""
    pass


@main.command()
@click.option("--config", "-c", default="config.yaml", help="Path to config file")
def serve(config):
    """Start Gcode agent service."""
    console.print(f"[bold green]Starting Gcode agent[/bold green]")
    console.print(f"Config: {config}")
    SessionManager().start_interactive()


@main.command()
@click.argument("runbook", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview without execution")
def run(runbook, dry_run):
    """Execute a runbook."""
    engine = RunbookEngine()
    if dry_run:
        console.print(f"[yellow]Dry run for: {runbook}[/yellow]")
        steps = engine.parse(runbook)
        for step in steps:
            console.print(f"  -> {step.name}")
    else:
        engine.execute(runbook)


@main.command()
@click.option("--type", "-t", "report_type", default="daily",
              type=click.Choice(["daily", "weekly", "incident"]))
@click.option("--output", "-o", default=None, help="Output file")
def report(report_type, output):
    """Generate ops report."""
    from gcode.report.reporter import Reporter
    r = Reporter()
    result = r.generate(report_type)
    if output:
        with open(output, "w") as f:
            f.write(result)
        console.print(f"[green]Report saved to {output}[/green]")
    else:
        console.print(result)


@main.command()
@click.argument("query")
def ask(query):
    """Ask Gcode a natural language question about your infrastructure."""
    session = SessionManager()
    response = session.ask(query)
    console.print(response)


if __name__ == "__main__":
    main()
