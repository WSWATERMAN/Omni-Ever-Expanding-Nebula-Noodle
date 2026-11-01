"""Tests for side-effect-free command plan formatting."""

import unittest

from goyathlay.planning import ExecutionPlan, render_plan


class PlanningTests(unittest.TestCase):
    def test_renders_all_decision_fields(self):
        rendered = render_plan(ExecutionPlan(
            "show ports", "ss -tulpn", "LOW", 75.0, "ALLOW", ("edge01", "edge02")
        ))
        for expected in ("show ports", "ss -tulpn", "LOW", "75", "ALLOW", "edge01", "edge02"):
            self.assertIn(expected, rendered)

    def test_unknown_reputation_is_explicit(self):
        plan = ExecutionPlan("list files", "ls -la", "LOW", None, "ALLOW")
        self.assertIn("Reputation:\nUnknown", render_plan(plan))


if __name__ == "__main__":
    unittest.main()
