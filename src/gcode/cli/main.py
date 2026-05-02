"""CLI entry point for Gcode ops agent.

Natural language first — just type `gcode` for interactive mode,
or `gcode "检查服务器状态"` to ask a question directly.
Sub-commands (check, report, run, alert, logpipe) are available for power users.
"""

import click
from rich.console import Console

from gcode.core.engine import RunbookEngine
from gcode.core.session import SessionManager

console = Console()


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="gcode")
@click.option("--config", "-c", "config_path", default="config.yaml",
              help="Path to config file")
@click.argument("query", required=False, nargs=-1)
@click.pass_context
def main(ctx, config_path, query):
    """Gcode — 麒麟OS 智能运维 Agent。

    自然语言交互:

    \b
        gcode                            # 进入交互式对话
        gcode "检查服务器状态"             # 单次自然语言查询
        gcode "nginx 重启会影响什么？"     # 自动调用运维工具

    \b
    运维命令（高级用法）:

        gcode check                      # 健康检查
        gcode report --type daily        # 日报
        gcode run runbook.yaml           # 执行 Runbook
    """
    if ctx.invoked_subcommand is not None:
        # 有子命令，透传
        return

    # 无子命令 → 自然语言模式
    if query:
        # 有关键词 → 单次查询
        session = SessionManager()
        response = session.ask(" ".join(query))
        console.print(response)
    else:
        # 无参数 → 交互式 REPL
        from gcode.core.config import load_config
        cfg = load_config(config_path)
        SessionManager(config=cfg).start_interactive()


@main.command()
@click.option("--config", "-c", "config_path", default="config.yaml",
              help="Path to config file")
def serve(config_path):
    """Start interactive REPL (same as running `gcode` without arguments)."""
    from gcode.core.config import load_config
    cfg = load_config(config_path)
    console.print(f"[bold green]Starting Gcode agent[/bold green]")
    console.print(f"Config: {config_path}")
    SessionManager(config=cfg).start_interactive()


@main.command()
@click.argument("runbook", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview without execution")
def run(runbook, dry_run):
    """Execute a runbook YAML file."""
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
@click.option("--output", "-o", default=None, help="Output file path")
def report(report_type, output):
    """Generate an operations report (daily / weekly / incident)."""
    from gcode.report.reporter import Reporter
    r = Reporter()
    result = r.generate(report_type)
    if output:
        with open(output, "w") as f:
            f.write(result)
        console.print(f"[green]Report saved to {output}[/green]")
    else:
        console.print(result)


@main.command(name="ask")
@click.argument("query", nargs=-1, required=True)
def ask_cmd(query):
    """Ask Gcode a natural language question (same as `gcode \"query\"`)."""
    session = SessionManager()
    response = session.ask(" ".join(query))
    console.print(response)


# Register sub-module commands
from gcode.monitor import register_commands as register_monitor
from gcode.alert import register_commands as register_alert
from gcode.logpipe import register_commands as register_logpipe
from gcode.alert.cli import alert as alert_cli_group
from gcode.logpipe.cli import logpipe as logpipe_cli_group

register_monitor(main)
register_alert(main)
register_logpipe(main)
main.add_command(alert_cli_group, name="alert-config")
main.add_command(logpipe_cli_group, name="logpipe")

if __name__ == "__main__":
    main()
