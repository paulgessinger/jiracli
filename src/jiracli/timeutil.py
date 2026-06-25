"""Small time-formatting helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def parse_jira_dt(value: str) -> datetime | None:
    """Parse a Jira ISO-8601 timestamp (e.g. ``2026-06-25T09:24:00.000+0200``)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        # Jira sometimes uses +0200 (no colon); fromisoformat handles most cases
        # on 3.11+, but guard anyway.
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")
        except ValueError:
            return None


def relative(value: str) -> str:
    """Human-friendly relative time, e.g. ``3h ago`` / ``2d ago``."""
    dt = parse_jira_dt(value)
    if dt is None:
        return value or ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        return "just now"
    if secs < 60:
        return f"{secs}s ago"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    return f"{days // 365}y ago"


def absolute(value: str) -> str:
    """Compact absolute timestamp for the detail view."""
    dt = parse_jira_dt(value)
    if dt is None:
        return value or ""
    return dt.strftime("%Y-%m-%d %H:%M")
