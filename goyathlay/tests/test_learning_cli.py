"""CLI-facing tests for the persona workflows."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from goyathlay.goyathlay import _handle_knowledge_command, _handle_operator_command, _trainer_feedback
from goyathlay.knowledge import KnowledgeBase
from goyathlay.rbac import RbacEngine, Role, UserContext


class LearningCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.knowledge = KnowledgeBase(Path(self.temp.name) / "knowledge.json")
        self.rbac = RbacEngine()

    def tearDown(self):
        self.temp.cleanup()

    def test_trainer_grade_flow_records_score_and_note(self):
        output = io.StringIO()
        with patch("builtins.input", side_effect=["5", "works cleanly"]), redirect_stdout(output):
            _trainer_feedback(self.knowledge, "show files", "linux", "ls", "README.md", "trainer")
        entry = self.knowledge.entries[0]
        self.assertEqual(entry.trainer_score, 5.0)
        self.assertIn("works cleanly", entry.notes[0])
        self.assertIn("Average: 5.00/5", output.getvalue())

    def test_sme_review_approves_candidate(self):
        self.knowledge.add_candidate("show users", "postgres", "SELECT usename FROM pg_user", "postgres")
        output = io.StringIO()
        with patch("builtins.input", side_effect=["A", "checked"]), redirect_stdout(output):
            handled = _handle_knowledge_command(
                "sme review", self.knowledge, UserContext("sme", Role.SME), self.rbac, "sme"
            )
        self.assertTrue(handled)
        self.assertTrue(self.knowledge.get_approved("show users", "postgres", "postgres").sme_approved)
        self.assertIn("Knowledge approved", output.getvalue())

    def test_operator_cannot_sme_approve(self):
        self.knowledge.add_candidate("show users", "postgres", "SELECT 1", "postgres")
        output = io.StringIO()
        with redirect_stdout(output):
            handled = _handle_knowledge_command(
                "sme review", self.knowledge, UserContext("operator", Role.OPERATOR), self.rbac, "sme"
            )
        self.assertTrue(handled)
        self.assertIn("review denied", output.getvalue())
        self.assertIsNone(self.knowledge.get_approved("show users", "postgres", "postgres"))

    def test_operator_cannot_switch_into_trainer_or_sme_persona(self):
        state = type("State", (), {"mode": "operator", "persona": "operator", "notice": ""})()
        output = io.StringIO()
        with redirect_stdout(output):
            handled = _handle_operator_command(
                "mode sme", profile_manager=None, current_profile=None,
                host_inventory=None, command_cache=None, audit_store=None,
                console_state=state, user_context=UserContext("operator", Role.OPERATOR),
                rbac_engine=self.rbac,
            )
        self.assertTrue(handled)
        self.assertEqual(state.persona, "operator")
        self.assertIn("RBAC denied", output.getvalue())

    def test_trainer_queue_lists_only_pending_entries(self):
        self.knowledge.add_candidate("show files", "linux", "ls")
        output = io.StringIO()
        with redirect_stdout(output):
            _handle_knowledge_command(
                "trainer queue", self.knowledge, UserContext("trainer", Role.TRAINER), self.rbac, "trainer"
            )
        self.assertIn("show files [linux/shell]: ls", output.getvalue())


if __name__ == "__main__":
    unittest.main()
