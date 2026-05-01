"""Policy evaluator -- runs check suites, thresholds, triggers alerts."""

import time
from dataclasses import dataclass, field
from typing import Callable

from gcode.monitor.checkers import CheckResult, Checker


@dataclass
class MonitorConfig:
    checks: list[dict] = field(default_factory=list)


@dataclass
class SuiteResult:
    timestamp: float
    results: list[CheckResult]
    duration_ms: float

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.status == "ok")

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.results if r.status == "warn")

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.status == "fail")

    @property
    def healthy(self) -> bool:
        return self.fail_count == 0


class Evaluator:
    """Runs a suite of health checks and evaluates overall health."""

    @staticmethod
    def run_checks(config: MonitorConfig) -> SuiteResult:
        start = time.time()
        results = []

        for item in config.checks:
            check_type = item["type"]
            kwargs = {k: v for k, v in item.items() if k != "type"}
            fn: Callable = getattr(Checker, check_type)
            result = fn(**kwargs)
            results.append(result)

        duration = (time.time() - start) * 1000
        return SuiteResult(timestamp=start, results=results, duration_ms=duration)

    @staticmethod
    def default_checks() -> MonitorConfig:
        return MonitorConfig(checks=[
            {"type": "disk", "path": "/"},
            {"type": "memory"},
            {"type": "tcp", "host": "localhost", "port": 22},
        ])
