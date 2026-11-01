"""Startup banner for the terminal operator console."""

from __future__ import annotations


HOTKEYS = (
    ("Ctrl+B", "Cache Bypass"),
    ("Ctrl+K", "AI Generation Bypass"),
    ("Ctrl+R", "Toggle Risk Display"),
    ("Ctrl+P", "Cycle Policy Profile"),
    ("Ctrl+T", "Toggle Audit Details"),
    ("Ctrl+I", "Inventory Summary"),
    ("Ctrl+H", "Help"),
)


def render_banner(
    *, engine: str, profile: str, role: str, audit_enabled: bool = True, tofu_enabled: bool = True
) -> str:
    """Return the plain-text startup banner and supported keyboard shortcuts."""
    lines = [
        "🚀 Goyathlay - Autonomous Operations Platform Initialized Successfully",
        "",
        "💡 Hotkeys:",
        *(f"[{key}] {label}" for key, label in HOTKEYS),
        "",
        "-" * 52,
        "",
        f"Engine: {engine}",
        f"Profile: {profile}",
        f"Role: {role}",
        f"Audit: {'Enabled' if audit_enabled else 'Unavailable'}",
        f"TOFU: {'Enabled' if tofu_enabled else 'Unavailable'}",
    ]
    return "\n".join(lines)
