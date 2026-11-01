"""Best-effort live operator status footer."""

from __future__ import annotations

import ast
from typing import Any
from pathlib import Path


class StatusBar:
    """Render a compact, refreshable status line for the active CLI state."""

    def __init__(self, state: Any) -> None:
        self.state = state

    def render(self) -> str:
        """Render active health and operational telemetry in one persistent line."""
        profile = self.state.profile_name()
        cache = "BYPASS" if self.state.cache_bypass else "ON"
        note = f" | {self.state.notice}" if self.state.notice else ""
        health = self.state.health
        health_message = self.state.health_message
        if health == "HEALTHY":
            health_text = "✔ HEALTHY"
        elif health == "CRITICAL":
            health_text = f"✖ HEALTH: CRITICAL | {health_message}"
        elif health == "DEGRADED":
            health_text = f"⚠ HEALTH: DEGRADED | {health_message}"
        else:
            health_text = f"⚠ HEALTH: {health} | {health_message}"
        return (
            f"{health_text} | ENGINE:{self.state.engine} | PROFILE:{profile} | "
            f"RBAC:{self.state.role} | AUDIT:ON | TOFU:ON | CACHE:{cache} | "
            f"MODE:{self.state.mode}{note}"
        )


def count_test_cases(test_directory: str | Path | None = None) -> int | None:
    """Count unittest-style test methods without importing or running tests."""
    directory = Path(test_directory) if test_directory else Path(__file__).resolve().parents[1] / "tests"
    if not directory.is_dir():
        return None
    count = 0
    try:
        for path in directory.rglob("test_*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            count += sum(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")
                for node in ast.walk(tree)
            )
    except (OSError, SyntaxError, UnicodeError):
        return None
    return count


def render_status_output(*, engine: str, profile: str, role: str, cache_enabled: bool,
                         audit_enabled: bool, tofu_enabled: bool, hosts: int,
                         groups: int, profiles: int, test_count: int | None = None,
                         version: str = "1.0.0", health: str = "UNKNOWN",
                         outstanding_issues: int = 0, last_healing_scan: str = "Never") -> str:
    """Render the explicit ``status`` command and current test-case count."""
    tests = "Unavailable" if test_count is None else str(test_count)
    return "\n".join([
        f"Version:        {version}", f"Engine:         {engine}",
        f"Profile:        {profile}", f"Role:           {role}",
        f"Cache:          {'Enabled' if cache_enabled else 'Unavailable'}",
        f"Audit:          {'Enabled' if audit_enabled else 'Unavailable'}",
        f"TOFU:           {'Enabled' if tofu_enabled else 'Unavailable'}",
        "",
        f"Hosts:          {hosts}", f"Groups:         {groups}",
        f"Profiles:       {profiles}", f"Test Count:     {tests}",
        f"Health:         {health}", f"Outstanding Issues: {outstanding_issues}",
        f"Last Healing Scan: {last_healing_scan}",
    ])
