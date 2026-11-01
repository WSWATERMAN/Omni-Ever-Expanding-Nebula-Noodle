"""Tests for explicit compensating-action planning."""

import unittest

from goyathlay.rollback import OperationKind, RollbackAction, RollbackPlanner


class RollbackPlannerTests(unittest.TestCase):
    def setUp(self):
        self.planner = RollbackPlanner()

    def test_file_change_requires_backup_and_plans_restore(self):
        missing = self.planner.plan([RollbackAction(OperationKind.FILE_CHANGE, "/etc/app.conf")])
        self.assertFalse(missing.steps)
        self.assertIn("No backup recorded", missing.blockers[0])
        plan = self.planner.plan([
            RollbackAction(OperationKind.FILE_CHANGE, "/etc/app.conf", "/var/backups/app.conf")
        ])
        self.assertEqual(plan.steps[0].command, "cp -- /var/backups/app.conf /etc/app.conf")

    def test_package_install_plans_supported_uninstall(self):
        plan = self.planner.plan([
            RollbackAction(OperationKind.PACKAGE_INSTALL, "nginx", package_manager="apt")
        ])
        self.assertEqual(plan.steps[0].command, "apt-get remove -- nginx")
        self.assertIn("dependencies", plan.steps[0].note)

    def test_unknown_package_manager_is_reported(self):
        plan = self.planner.plan([
            RollbackAction(OperationKind.PACKAGE_INSTALL, "nginx", package_manager="unknown")
        ])
        self.assertFalse(plan.steps)
        self.assertTrue(plan.blockers)

    def test_service_restart_is_labeled_as_compensation(self):
        plan = self.planner.plan([RollbackAction(OperationKind.SERVICE_RESTART, "web.service")])
        self.assertEqual(plan.steps[0].command, "systemctl restart web.service")
        self.assertIn("cannot restore prior runtime state", plan.steps[0].note)

    def test_plan_reverses_operation_order_and_quotes_targets(self):
        plan = self.planner.plan([
            RollbackAction(OperationKind.SERVICE_RESTART, "web service"),
            RollbackAction(OperationKind.PACKAGE_INSTALL, "pkg name", package_manager="dnf"),
        ])
        self.assertIn("'pkg name'", plan.steps[0].command)
        self.assertEqual(plan.steps[1].target, "web service")


if __name__ == "__main__":
    unittest.main()
