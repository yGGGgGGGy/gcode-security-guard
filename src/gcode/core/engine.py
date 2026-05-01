"""Runbook execution engine."""

import subprocess
import yaml
from dataclasses import dataclass, field
from typing import Optional
from rich.console import Console

console = Console()


@dataclass
class Step:
    name: str
    command: str
    timeout: int = 30
    retry: int = 0
    rollback: Optional[str] = None


@dataclass
class StepResult:
    step: Step
    exit_code: int
    stdout: str
    stderr: str
    attempts: int = 1

    @property
    def ok(self):
        return self.exit_code == 0


@dataclass
class Runbook:
    name: str
    description: str = ""
    steps: list[Step] = field(default_factory=list)


class RunbookEngine:
    """Parses and executes runbooks defined in YAML."""

    def parse(self, path: str) -> list[Step]:
        with open(path) as f:
            data = yaml.safe_load(f)

        steps = []
        for item in data.get("steps", []):
            steps.append(Step(
                name=item["name"],
                command=item["command"],
                timeout=item.get("timeout", 30),
                retry=item.get("retry", 0),
                rollback=item.get("rollback"),
            ))
        return steps

    def execute(self, path: str) -> list[StepResult]:
        steps = self.parse(path)
        results = []

        for step in steps:
            result = self._run_step(step)
            results.append(result)

            if not result.ok:
                console.print(f"[red]FAIL: {step.name}[/red]")
                if step.rollback:
                    console.print(f"[yellow]Rolling back: {step.rollback}[/yellow]")
                    self._run_command(step.rollback, step.timeout)
                break
            console.print(f"[green]OK: {step.name}[/green]")

        return results

    def _run_step(self, step: Step) -> StepResult:
        for attempt in range(1 + step.retry):
            exit_code, stdout, stderr = self._run_command(step.command, step.timeout)
            if exit_code == 0:
                return StepResult(step, exit_code, stdout, stderr, attempt + 1)
            console.print(f"[yellow]Retry {attempt + 1}/{step.retry}: {step.name}[/yellow]")
        return StepResult(step, exit_code, stdout, stderr, 1 + step.retry)

    def _run_command(self, cmd: str, timeout: int) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Command timed out after {timeout}s"
