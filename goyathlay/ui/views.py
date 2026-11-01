"""Plain-text operator review plans."""

from __future__ import annotations

from typing import Iterable


RULE = "-" * 52


def render_execution_plan(
    *, intent: str, command: str, targets: Iterable[str] = (), engine: str,
    profile: str, role: str, risk: str, reasons: Iterable[str] = (),
    reputation: float | None = None, policy: str, policy_reasons: Iterable[str] = (),
    show_risk: bool = True,
) -> str:
    """Render the complete command and governance decision before approval."""
    target_rows = list(targets) or ["local"]
    risk_reasons = list(reasons) or ["No known risky patterns detected."]
    policy_notes = list(policy_reasons) or ["No policy concerns detected."]
    reputation_text = "Unknown" if reputation is None else f"{reputation:g}"
    return "\n".join([
        RULE, "EXECUTION PLAN", RULE, "", f"Intent:\n{intent}",
        f"Generated Command:\n{command}", f"Command:\n{command}",
        "Targets:", *(f"- {item}" for item in target_rows),
        f"Engine:\n{engine}", f"Profile:\n{profile}", f"Role:\n{role}",
        *([f"Risk:\n{risk}", f"Risk Level:\n{risk}", "Reasons:",
           *(f"- {item}" for item in risk_reasons)] if show_risk else
          ["Risk assessment is hidden; enforcement remains active."]),
        f"Reputation:\n{reputation_text}",
        f"Policy:\n{policy}", f"Decision:\n{policy}", "Policy Reasons:",
        *(f"- {item}" for item in policy_notes), RULE,
    ])


def render_database_plan(*, engine: str, profile: str, sql: str, risk: str, validation: str,
                         target: str | None = None, show_risk: bool = True) -> str:
    """Render a read-only database query review screen."""
    return "\n".join([
        RULE, "DATABASE PLAN", RULE, f"Database: {engine}", f"Engine:\n{engine}",
        f"Profile:\n{profile}", *([f"Host:\n{target}"] if target and engine == "PostgreSQL" else []),
        *([f"Database:\n{target}"] if target and engine == "SQLite" else []),
        "Generated SQL:", sql,
        *([f"Risk:\n{risk}"] if show_risk else ["Risk assessment is hidden; enforcement remains active."]),
        f"Validation:\n{validation}", RULE,
    ])


def render_network_plan(*, vendor: str, command: str, risk: str) -> str:
    """Render a network-device command plan for future interpreter integration."""
    return "\n".join([
        RULE, "NETWORK PLAN", RULE, f"Vendor:\n{vendor}",
        "Generated Command:", command, f"Risk:\n{risk}", RULE,
    ])
