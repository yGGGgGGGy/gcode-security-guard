"""Centralized config loading from config.yaml with defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")


@dataclass
class MonitorConfig:
    checks: list[dict] = field(default_factory=lambda: [
        {"type": "disk", "path": "/"},
        {"type": "memory"},
        {"type": "tcp", "host": "localhost", "port": 22},
    ])


@dataclass
class AlertConfig:
    auto_fire: bool = True
    cooldown_seconds: int = 300
    channels: list[dict] = field(default_factory=lambda: [
        {"channel": "stdout", "enabled": True},
    ])


@dataclass
class LogpipeConfig:
    sources: list[dict] = field(default_factory=list)
    anomaly_threshold: int = 10


@dataclass
class SocketConfig:
    m1_path: str = "/run/gcode/gcode.sock"
    dp1_path: str = "/run/gcode/gcode-dp1.sock"


@dataclass
class ReasonerConfig:
    provider: str = "ollama"
    model: str = "qwen2.5:7b"
    api_key: str = ""
    base_url: str = ""
    max_tool_rounds: int = 3
    timeout: int = 30


@dataclass
class GcodeConfig:
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    alert: AlertConfig = field(default_factory=AlertConfig)
    logpipe: LogpipeConfig = field(default_factory=LogpipeConfig)
    socket: SocketConfig = field(default_factory=SocketConfig)
    reasoner: ReasonerConfig = field(default_factory=ReasonerConfig)


def load_config(path: str | Path | None = None) -> GcodeConfig:
    """Load config from YAML file, falling back to defaults for missing keys."""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.exists():
        return GcodeConfig()

    with open(p) as f:
        raw = yaml.safe_load(f) or {}

    cfg = GcodeConfig()

    if "monitor" in raw:
        m = raw["monitor"]
        if "checks" in m:
            cfg.monitor.checks = m["checks"]

    if "alert" in raw:
        a = raw["alert"]
        cfg.alert.auto_fire = a.get("auto_fire", cfg.alert.auto_fire)
        cfg.alert.cooldown_seconds = a.get("cooldown_seconds", cfg.alert.cooldown_seconds)
        if "channels" in a:
            cfg.alert.channels = a["channels"]

    if "logpipe" in raw:
        lp = raw["logpipe"]
        if "sources" in lp:
            cfg.logpipe.sources = lp["sources"]
        cfg.logpipe.anomaly_threshold = lp.get("anomaly_threshold", cfg.logpipe.anomaly_threshold)

    if "socket" in raw:
        s = raw["socket"]
        cfg.socket.m1_path = s.get("m1_path", cfg.socket.m1_path)
        cfg.socket.dp1_path = s.get("dp1_path", cfg.socket.dp1_path)

    if "reasoner" in raw:
        r = raw["reasoner"]
        cfg.reasoner.provider = r.get("provider", cfg.reasoner.provider)
        cfg.reasoner.model = r.get("model", cfg.reasoner.model)
        cfg.reasoner.api_key = r.get("api_key", cfg.reasoner.api_key)
        cfg.reasoner.base_url = r.get("base_url", cfg.reasoner.base_url)
        cfg.reasoner.max_tool_rounds = r.get("max_tool_rounds", cfg.reasoner.max_tool_rounds)
        cfg.reasoner.timeout = r.get("timeout", cfg.reasoner.timeout)

    # API key 环境变量覆盖（密钥不应写入 YAML）
    cfg.reasoner.api_key = os.environ.get("GCODE_REASONER_API_KEY", cfg.reasoner.api_key)

    return cfg
