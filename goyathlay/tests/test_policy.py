import unittest
from unittest.mock import patch

from goyathlay.goyathlay import _confirm_policy_override
from goyathlay.policy import PolicyDecision, PolicyEngine
from goyathlay.risk import RiskLevel


class PolicyEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine()

    def test_allow_low_risk_with_good_reputation(self):
        result = self.engine.evaluate(RiskLevel.LOW, 25)

        self.assertEqual(result.decision, PolicyDecision.ALLOW)

    def test_allow_low_risk_with_unknown_reputation(self):
        result = self.engine.evaluate(RiskLevel.LOW, None)

        self.assertEqual(result.decision, PolicyDecision.ALLOW)

    def test_medium_risk_requires_extra_confirmation_for_any_positive_score(self):
        for reputation in (None, 100, 25, 24, 1):
            with self.subTest(reputation=reputation):
                result = self.engine.evaluate(RiskLevel.MEDIUM, reputation)
                self.assertEqual(result.decision, PolicyDecision.REQUIRE_EXTRA_CONFIRMATION)
                self.assertIn("Medium risk operation", result.reasons)

    def test_high_risk_requires_extra_confirmation(self):
        result = self.engine.evaluate(RiskLevel.HIGH, 50)

        self.assertEqual(result.decision, PolicyDecision.REQUIRE_EXTRA_CONFIRMATION)
        self.assertIn("High risk command", result.reasons)

    def test_high_risk_with_poor_reputation_is_denied(self):
        result = self.engine.evaluate(RiskLevel.HIGH, 7)

        self.assertEqual(result.decision, PolicyDecision.DENY)
        self.assertIn("High risk command", result.reasons)
        self.assertIn("Poor command reputation", result.reasons)

    def test_zero_reputation_is_denied_for_any_risk_level(self):
        for level in RiskLevel:
            with self.subTest(level=level):
                result = self.engine.evaluate(level, 0)
                self.assertEqual(result.decision, PolicyDecision.DENY)

    def test_poor_reputation_requires_extra_confirmation(self):
        result = self.engine.evaluate(RiskLevel.LOW, 24)

        self.assertEqual(result.decision, PolicyDecision.REQUIRE_EXTRA_CONFIRMATION)
        self.assertIn("Poor command reputation", result.reasons)

    def test_reasons_accumulate(self):
        result = self.engine.evaluate(RiskLevel.HIGH, 7)

        self.assertEqual(
            result.reasons,
            ["High risk command", "Poor command reputation"],
        )

    def test_reputation_outside_expected_range_is_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate(RiskLevel.LOW, 101)

    @patch("builtins.input", return_value="OVERRIDE")
    def test_override_confirmation_is_accepted(self, mocked_input):
        self.assertTrue(_confirm_policy_override())
        mocked_input.assert_called_once_with("Type OVERRIDE to continue: ")

    @patch("builtins.input", return_value="override")
    def test_non_override_confirmation_is_cancelled(self, mocked_input):
        self.assertFalse(_confirm_policy_override())
        mocked_input.assert_called_once_with("Type OVERRIDE to continue: ")


if __name__ == "__main__":
    unittest.main()
