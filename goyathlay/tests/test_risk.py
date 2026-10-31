import unittest
from unittest.mock import patch

from goyathlay.goyathlay import _confirm_high_risk
from goyathlay.risk import RiskEngine, RiskLevel


class RiskEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = RiskEngine()

    def test_low_risk_command(self):
        assessment = self.engine.assess("ss -tulpn")

        self.assertEqual(assessment.level, RiskLevel.LOW)
        self.assertEqual(assessment.reasons, [])

    def test_medium_risk_command(self):
        assessment = self.engine.assess("systemctl restart nginx")

        self.assertEqual(assessment.level, RiskLevel.MEDIUM)
        self.assertIn("Service restart", assessment.reasons)

    def test_high_risk_command(self):
        assessment = self.engine.assess("rm -rf /tmp/test")

        self.assertEqual(assessment.level, RiskLevel.HIGH)
        self.assertIn("Recursive force deletion", assessment.reasons)

    def test_returns_multiple_reasons_and_highest_level(self):
        assessment = self.engine.assess("apt install test && rm -rf /tmp/test && reboot")

        self.assertEqual(assessment.level, RiskLevel.HIGH)
        self.assertIn("Package manager operation", assessment.reasons)
        self.assertIn("Recursive force deletion", assessment.reasons)
        self.assertIn("System shutdown or reboot", assessment.reasons)

    def test_empty_command_has_low_level_and_reason(self):
        assessment = self.engine.assess("  \n")

        self.assertEqual(assessment.level, RiskLevel.LOW)
        self.assertIn("Empty command.", assessment.reasons)

    def test_matching_is_case_insensitive(self):
        assessment = self.engine.assess("RM -RF /tmp/test")

        self.assertEqual(assessment.level, RiskLevel.HIGH)

    def test_detects_fork_bomb(self):
        assessment = self.engine.assess(":(){ :|:& };:")

        self.assertEqual(assessment.level, RiskLevel.HIGH)
        self.assertIn("Fork bomb pattern", assessment.reasons)

    @patch("builtins.input", return_value="EXECUTE")
    def test_exact_execute_confirmation_is_accepted(self, mocked_input):
        self.assertTrue(_confirm_high_risk())
        mocked_input.assert_called_once_with("Type EXECUTE to continue: ")

    @patch("builtins.input", return_value="execute")
    def test_non_execute_confirmation_is_rejected(self, mocked_input):
        self.assertFalse(_confirm_high_risk())
        mocked_input.assert_called_once_with("Type EXECUTE to continue: ")


if __name__ == "__main__":
    unittest.main()
