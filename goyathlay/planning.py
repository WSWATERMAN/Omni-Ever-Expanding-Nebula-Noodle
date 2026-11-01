"""Immutable previews of command decisions without approval or execution."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionPlan:
    """A reviewable summary of a proposed operation."""

    intent: str
    command: str
    risk: str
    reputation: float | None
    policy: str
    targets: tuple[str, ...] = ()


def render_plan(plan: ExecutionPlan) -> str:
    """Format a plan as plain terminal text."""
    reputation = "Unknown" if plan.reputation is None else f"{plan.reputation:g}"
    targets = "\n".join(f"- {target}" for target in plan.targets) if plan.targets else "- local"
    return (
        f"Intent:\n{plan.intent}\n\nCommand:\n{plan.command}\n\nRisk:\n{plan.risk}\n\n"
        f"Reputation:\n{reputation}\n\nPolicy:\n{plan.policy}\n\nTargets:\n{targets}"
    )
