"""Notification dispatch — stdout, webhook channels."""

from __future__ import annotations

from rich.console import Console

from .models import AlertEvent

console = Console()


def notify(event: AlertEvent, channels: list[dict]) -> None:
    """Send alert event through all matching channels."""
    text = f"[Gcode Alert] {event.monitor_name}: {event.message}"

    for ch in channels:
        if not ch.get("enabled"):
            continue
        if ch["channel"] == "stdout":
            _notify_stdout(text, event)
        elif ch["channel"] == "webhook" and ch.get("target"):
            _notify_webhook(ch["target"], text, event)


def _notify_stdout(text: str, event: AlertEvent) -> None:
    prefix = "[bold red]ALERT[/]" if event.status.value == "firing" else "[bold green]RESOLVED[/]"
    console.print(f"{prefix} {text}")


def _notify_webhook(url: str, text: str, event: AlertEvent) -> None:
    try:
        import httpx
        payload = {
            "text": text,
            "status": event.status.value,
            "monitor": event.monitor_name,
            "rule": event.rule_name,
        }
        httpx.post(url, json=payload, timeout=5)
    except Exception:
        pass
