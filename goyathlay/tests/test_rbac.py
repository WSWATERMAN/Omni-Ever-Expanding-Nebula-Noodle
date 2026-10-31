"""Tests for local role-based command authorization."""

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from goyathlay import goyathlay
from goyathlay.rbac import AuthorizationDecision, RbacEngine, Role, UserContext
from goyathlay.risk import RiskLevel


class RbacEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = RbacEngine()

    def test_role_risk_matrix(self):
        cases = (
            (Role.VIEWER, RiskLevel.LOW, AuthorizationDecision.ALLOW),
            (Role.VIEWER, RiskLevel.MEDIUM, AuthorizationDecision.DENY),
            (Role.VIEWER, RiskLevel.HIGH, AuthorizationDecision.DENY),
            (Role.OPERATOR, RiskLevel.LOW, AuthorizationDecision.ALLOW),
            (Role.OPERATOR, RiskLevel.MEDIUM, AuthorizationDecision.ALLOW),
            (Role.OPERATOR, RiskLevel.HIGH, AuthorizationDecision.REQUIRE_OVERRIDE),
            (Role.ADMIN, RiskLevel.LOW, AuthorizationDecision.ALLOW),
            (Role.ADMIN, RiskLevel.MEDIUM, AuthorizationDecision.ALLOW),
            (Role.ADMIN, RiskLevel.HIGH, AuthorizationDecision.ALLOW),
        )
        for role, risk, expected in cases:
            with self.subTest(role=role, risk=risk):
                self.assertIs(
                    self.engine.authorize(UserContext("scott", role), risk), expected
                )

    def test_role_override_acceptance(self):
        user = UserContext("scott", Role.OPERATOR)
        with patch.object(self.engine, "authorize", return_value=AuthorizationDecision.REQUIRE_OVERRIDE), patch(
            "builtins.input", return_value="ROLE-OVERRIDE"
        ), redirect_stdout(io.StringIO()):
            decision = goyathlay._authorize_command(self.engine, user, RiskLevel.HIGH)
        self.assertIs(decision, AuthorizationDecision.REQUIRE_OVERRIDE)

    def test_role_override_cancellation(self):
        user = UserContext("scott", Role.OPERATOR)
        output = io.StringIO()
        with patch.object(self.engine, "authorize", return_value=AuthorizationDecision.REQUIRE_OVERRIDE), patch(
            "builtins.input", return_value="anything else"
        ), redirect_stdout(output):
            decision = goyathlay._authorize_command(self.engine, user, RiskLevel.HIGH)
        self.assertIs(decision, AuthorizationDecision.DENY)
        self.assertIn("Role override cancelled.", output.getvalue())

    def test_default_user_context_is_local_admin(self):
        user = UserContext(username="local", role=Role.ADMIN)
        self.assertIs(self.engine.authorize(user, RiskLevel.HIGH), AuthorizationDecision.ALLOW)


if __name__ == "__main__":
    unittest.main()
