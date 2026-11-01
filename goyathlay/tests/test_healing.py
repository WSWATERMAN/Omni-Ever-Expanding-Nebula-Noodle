"""Tests for read-only healing diagnostics and approval-gated repairs."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from goyathlay.healing import (
    HealingManager,
    ProposedRepair,
)


class HealingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.runner = Mock(return_value=Mock(returncode=0, stdout="NAME ID SIZE MODIFIED\n", stderr=""))
        self.manager = HealingManager(
            home=self.home,
            module_available=lambda name: name != "ollama",
            which=lambda name: "/usr/bin/ollama",
            runner=self.runner,
            emit=Mock(),
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_proposed_repair_serialization(self):
        repair = ProposedRepair("Missing package", "Install it", "pip install x", "LOW", True)
        self.assertEqual(repair.to_dict(), {
            "issue": "Missing package", "repair": "Install it", "command": "pip install x",
            "requires_network": True, "risk": "LOW",
        })

    def test_plan_generation_and_render(self):
        plan = self.manager.scan()
        self.assertIn("generated_at", plan)
        self.assertTrue(any(row["issue"] == "Missing Ollama package" for row in plan["issues"]))
        output = self.manager.render(plan)
        self.assertIn("HEALING DRY RUN", output)
        self.assertIn("Issues Found:", output)
        self.assertIn("No changes were made.", output)

    def test_dry_run_has_no_files_or_repair_side_effects(self):
        plan = self.manager.scan()
        self.manager.render(plan)
        self.assertFalse(self.manager.config_dir.exists())
        self.runner.assert_called_once_with(
            ["/usr/bin/ollama", "list"], capture_output=True,
            text=True, check=False, timeout=10,
        )
        self.assertFalse(any("pip" in str(call) or "pull" in str(call) for call in self.runner.call_args_list))

    def test_plan_file_created_only_on_explicit_save(self):
        path = self.manager.save_plan(self.manager.scan())
        self.assertEqual(path, self.home / ".goyathlay" / "healing-plan.json")
        self.assertEqual(json.loads(path.read_text())["issues"], self.manager._last_plan["issues"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_review_approval_applies_allowlisted_repair(self):
        approved = {"issue": "Missing Ollama package", "repair": "Install Python package",
                    "command": f"{__import__('sys').executable} -m pip install ollama",
                    "risk": "LOW", "requires_network": True}
        plan = {"generated_at": "now", "issues": [approved]}
        self.manager.input_fn = lambda prompt: "Y"
        self.manager.runner = Mock(return_value=Mock(returncode=0, stdout="", stderr=""))
        self.manager._apply = Mock(return_value=True)
        result = self.manager.review(plan)
        self.manager._apply.assert_called_once_with(approved)
        self.assertIsInstance(result, dict)
        audit = self.manager.read_audit()
        self.assertEqual(audit[0].mode, "review")

    def test_review_rejection_does_not_apply(self):
        repair = {"issue": "Missing Ollama package", "repair": "Install Python package",
                  "command": "pip install ollama", "risk": "LOW", "requires_network": True}
        self.manager.input_fn = lambda prompt: "N"
        self.manager._apply = Mock()
        self.manager.review({"generated_at": "now", "issues": [repair]})
        self.manager._apply.assert_not_called()
        self.assertEqual(self.manager.read_audit()[0].issue, "Missing Ollama package")

    def test_audit_record_creation(self):
        record = self.manager.audit_record("Issue", "Repair", "dry-run")
        self.assertEqual(record.issue, "Issue")
        self.assertEqual(record.mode, "dry-run")

    def test_corrupt_trust_and_auth_data_are_high_risk(self):
        self.manager.config_dir.mkdir()
        (self.manager.config_dir / "trust_store.json").write_text("not json")
        (self.manager.config_dir / "users.json").write_text("{}")
        plan = self.manager.scan()
        high = [item for item in plan["issues"] if item["risk"] == "HIGH"]
        self.assertEqual(len(high), 2)


if __name__ == "__main__":
    unittest.main()
