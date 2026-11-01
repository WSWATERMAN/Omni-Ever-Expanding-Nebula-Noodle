"""Deterministic policy decisions from command risk and reputation."""

from dataclasses import dataclass
from enum import Enum

if __package__:
    from .risk import RiskLevel
    from .profiles import PolicyProfile
else:
    from risk import RiskLevel
    from profiles import PolicyProfile


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
        profile: PolicyProfile | None = None,
    ) -> PolicyResult:
        """Evaluate a command using profile constraints or legacy defaults."""
        if not isinstance(risk_level, RiskLevel):
            raise TypeError("risk_level must be a RiskLevel.")
        if reputation_score is not None and not 0 <= reputation_score <= 100:
            raise ValueError("reputation_score must be between 0 and 100.")

        if profile is not None:
            if not isinstance(profile, PolicyProfile):
                raise TypeError("profile must be a PolicyProfile or None.")
            return self._evaluate_profile(risk_level, reputation_score, profile)

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

    @staticmethod
    def _evaluate_profile(
        risk_level: RiskLevel,
        reputation_score: float | None,
        profile: PolicyProfile,
    ) -> PolicyResult:
        """Apply the selected profile's risk and reputation thresholds."""
        reasons: list[str] = []
        decision = PolicyDecision.ALLOW

        if risk_level is RiskLevel.HIGH:
            if not profile.allow_high_risk:
                reasons.append(f"{profile.name.title()} profile blocks high-risk commands")
                decision = PolicyDecision.DENY
            elif profile.minimum_reputation > 0 and profile.allow_override:
                reasons.append(f"{profile.name.title()} profile requires override for high-risk commands")
                decision = PolicyDecision.REQUIRE_EXTRA_CONFIRMATION

        if reputation_score is not None and reputation_score < profile.minimum_reputation:
            reasons.append(
                f"Reputation {reputation_score:g} is below the profile minimum "
                f"of {profile.minimum_reputation}"
            )
            if profile.allow_override:
                if decision is not PolicyDecision.DENY:
                    decision = PolicyDecision.REQUIRE_EXTRA_CONFIRMATION
            else:
                decision = PolicyDecision.DENY

        if decision is not PolicyDecision.ALLOW:
            return PolicyResult(decision, reasons)

        # Profiles that explicitly allow high risk with no reputation floor
        # are the permissive development/emergency presets.
        if profile.allow_high_risk and profile.allow_override and profile.minimum_reputation == 0:
            return PolicyResult(PolicyDecision.ALLOW, [])

        # Preserve the existing baseline controls for cases the profile does
        # not specify, such as medium-risk operations.
        return PolicyEngine().evaluate(risk_level, reputation_score)
