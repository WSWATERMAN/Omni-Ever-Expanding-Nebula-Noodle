"""Best-effort live operator status footer."""

from __future__ import annotations

from typing import Any


def _metrics() -> tuple[str, str]:
    """Return CPU and memory percentages, degrading cleanly without psutil."""
    try:
        import psutil

        return f"{psutil.cpu_percent(interval=None):.1f}%", f"{psutil.virtual_memory().percent:.1f}%"
    except Exception:
        return "n/a", "n/a"


class StatusBar:
    """Render a compact, refreshable status line for the active CLI state."""

    def __init__(self, state: Any) -> None:
        self.state = state

    def render(self) -> str:
        """Render current engine, governance flags, and optional system metrics."""
        cpu, ram = _metrics()
        profile = self.state.profile_name()
        cache = "BYPASS" if self.state.cache_bypass else "ON"
        risk = "ON" if self.state.show_risk else "HIDDEN"
        audit_details = "ON" if self.state.show_audit_details else "OFF"
        note = f" | {self.state.notice}" if self.state.notice else ""
        return (
            f"GOYATHLAY SHELL | ENGINE:{self.state.engine} | PROFILE:{profile} | "
            f"RBAC:{self.state.role} | CACHE:{cache} | RISK:{risk} | AUDIT:ON/{audit_details} | TOFU:ON | "
            f"CPU:{cpu} | RAM:{ram}{note}"
        )


def render_status_output(*, engine: str, profile: str, role: str, cache_enabled: bool,
                         audit_enabled: bool, tofu_enabled: bool, hosts: int,
                         groups: int, profiles: int) -> str:
    """Render the explicit ``status`` command without inventing test counts."""
    return "\n".join([
        f"Engine:         {engine}", f"Profile:        {profile}", f"RBAC:           {role}",
        f"Cache:          {'Enabled' if cache_enabled else 'Unavailable'}",
        f"Audit:          {'Enabled' if audit_enabled else 'Unavailable'}",
        f"TOFU:           {'Enabled' if tofu_enabled else 'Unavailable'}", "",
        f"Hosts:          {hosts}", f"Groups:         {groups}",
        f"Profiles:       {profiles}", "Version:        1.0.0",
        "Tests:          Run python3 -m unittest discover -s goyathlay/tests -v",
    ])
