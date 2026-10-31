"""Deterministic policy decisions from command risk and reputation."""

from dataclasses import dataclass
from enum import Enum

if __package__:
    from .risk import RiskLevel
else:
    from risk import RiskLevel


class PolicyDecision(Enum):
    """Whether a command may proceed through approval."""

    ALLOW = "allow"
    REQUIRE_EXTRA_CONFIRMATION = "require_extra_confirmation"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyResult:
    """Policy outcome with human-readable reasons."""

    decision: PolicyDecision
    reasons: list[str]


class PolicyEngine:
    """Apply fixed risk and reputation thresholds without external services."""

    def evaluate(
        self,
        risk_level: RiskLevel,
        reputation_score: float | None,
    ) -> PolicyResult:
        """Evaluate a command using risk severity and its optional score."""
        if not isinstance(risk_level, RiskLevel):
            raise TypeError("risk_level must be a RiskLevel.")
        if reputation_score is not None and not 0 <= reputation_score <= 100:
            raise ValueError("reputation_score must be between 0 and 100.")

        reasons: list[str] = []
        if risk_level is RiskLevel.HIGH:
            reasons.append("High risk command")
        elif risk_level is RiskLevel.MEDIUM:
            reasons.append("Medium risk operation")

        if reputation_score == 0:
            reasons.append("Command reputation is zero")
            return PolicyResult(PolicyDecision.DENY, reasons)

        if reputation_score is not None and reputation_score < 25:
            reasons.append("Poor command reputation")

        if risk_level is RiskLevel.HIGH and reputation_score is not None and reputation_score < 10:
            return PolicyResult(PolicyDecision.DENY, reasons)

        if risk_level is RiskLevel.MEDIUM:
            return PolicyResult(PolicyDecision.REQUIRE_EXTRA_CONFIRMATION, reasons)
        if reputation_score is not None and reputation_score < 25:
            return PolicyResult(PolicyDecision.REQUIRE_EXTRA_CONFIRMATION, reasons)
        if risk_level is RiskLevel.HIGH:
            return PolicyResult(PolicyDecision.REQUIRE_EXTRA_CONFIRMATION, reasons)

        return PolicyResult(PolicyDecision.ALLOW, reasons)
