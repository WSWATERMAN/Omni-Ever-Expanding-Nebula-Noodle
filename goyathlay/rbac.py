"""Local role-based authorization for command risk levels."""

from dataclasses import dataclass
from enum import Enum

if __package__:
    from .risk import RiskLevel
else:  # Support direct script imports.
    from risk import RiskLevel


class Role(Enum):
    """Application roles supported by the local authorization engine."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    TRAINER = "trainer"
    SME = "sme"
    ADMIN = "admin"


@dataclass(frozen=True)
class UserContext:
    """Locally supplied identity and role; this is not authentication."""

    username: str
    role: Role

    def __post_init__(self) -> None:
        if not self.username.strip():
            raise ValueError("username must not be empty.")
        if not isinstance(self.role, Role):
            raise TypeError("role must be a Role.")


class AuthorizationDecision(Enum):
    """RBAC result used to gate the policy and approval stages."""

    ALLOW = "allow"
    REQUIRE_OVERRIDE = "require_override"
    DENY = "deny"


class RbacEngine:
    """Apply a deterministic role-by-risk authorization matrix."""

    _DECISIONS = {
        Role.VIEWER: {
            RiskLevel.LOW: AuthorizationDecision.ALLOW,
            RiskLevel.MEDIUM: AuthorizationDecision.DENY,
            RiskLevel.HIGH: AuthorizationDecision.DENY,
        },
        Role.OPERATOR: {
            RiskLevel.LOW: AuthorizationDecision.ALLOW,
            RiskLevel.MEDIUM: AuthorizationDecision.ALLOW,
            RiskLevel.HIGH: AuthorizationDecision.REQUIRE_OVERRIDE,
        },
        Role.ADMIN: {
            RiskLevel.LOW: AuthorizationDecision.ALLOW,
            RiskLevel.MEDIUM: AuthorizationDecision.ALLOW,
            RiskLevel.HIGH: AuthorizationDecision.ALLOW,
        },
        Role.TRAINER: {
            RiskLevel.LOW: AuthorizationDecision.ALLOW,
            RiskLevel.MEDIUM: AuthorizationDecision.ALLOW,
            RiskLevel.HIGH: AuthorizationDecision.REQUIRE_OVERRIDE,
        },
        Role.SME: {
            RiskLevel.LOW: AuthorizationDecision.ALLOW,
            RiskLevel.MEDIUM: AuthorizationDecision.ALLOW,
            RiskLevel.HIGH: AuthorizationDecision.REQUIRE_OVERRIDE,
        },
    }

    _LEARNING_PERMISSIONS = {
        "feedback": {Role.OPERATOR, Role.TRAINER, Role.SME, Role.ADMIN},
        "grade": {Role.TRAINER, Role.SME, Role.ADMIN},
        "approve": {Role.SME, Role.ADMIN},
    }

    def authorize(self, user: UserContext, risk_level: RiskLevel) -> AuthorizationDecision:
        """Return the authorization decision for a user and assessed risk."""
        if not isinstance(user, UserContext):
            raise TypeError("user must be a UserContext.")
        if not isinstance(risk_level, RiskLevel):
            raise TypeError("risk_level must be a RiskLevel.")
        return self._DECISIONS[user.role][risk_level]

    def authorize_learning(self, user: UserContext, action: str) -> bool:
        """Check persona permissions for learning actions, independent of risk."""
        if action not in self._LEARNING_PERMISSIONS:
            raise ValueError(f"Unknown learning action: {action}")
        return user.role in self._LEARNING_PERMISSIONS[action]
