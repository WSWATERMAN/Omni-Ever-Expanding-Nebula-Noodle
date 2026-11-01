"""Tests for operator/trainer/SME learning and legacy import."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goyathlay.knowledge import KnowledgeBase, KnowledgeStatus
from goyathlay.knowledge.migration import migrate_legacy_data
from goyathlay.knowledge.review_queue import ReviewQueue
from goyathlay.rbac import RbacEngine, Role, UserContext


class KnowledgeArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = KnowledgeBase(self.root / "knowledge.json")

    def tearDown(self):
        self.temp.cleanup()

    def test_operator_feedback_tracks_outcomes(self):
        entry = self.store.record_operator_feedback("show files", "linux", "ls", "success")
        entry = self.store.record_operator_feedback("show files", "linux", "ls", "failure")
        self.assertEqual((entry.success_count, entry.failure_count), (1, 1))
        self.assertFalse(entry.sme_approved)

    def test_trainer_grading_averages_and_saves_notes(self):
        self.store.record_trainer_grade("show files", "linux", "ls", 5, "clear", "trainer-a")
        entry = self.store.record_trainer_grade("show files", "linux", "ls", 3, "", "trainer-b")
        self.assertEqual(entry.trainer_score, 4.0)
        self.assertEqual(entry.trainer_review_count, 2)
        self.assertIn("note:clear", entry.notes[0])

    def test_reputation_combines_operator_trainer_and_sme_evidence(self):
        self.store.record_operator_feedback("show files", "linux", "ls", "success")
        self.store.record_operator_feedback("show files", "linux", "ls", "failure")
        self.store.record_trainer_grade("show files", "linux", "ls", 4)
        entry = self.store.entries[0]
        self.assertEqual(entry.reputation_score, 65.0)
        entry = self.store.decide("show files", "linux", "ls", KnowledgeStatus.APPROVED)
        self.assertEqual(entry.reputation_score, 76.67)

    def test_sme_approval_required_for_lookup(self):
        entry = self.store.add_candidate("show files", "linux", "ls")
        self.assertIsNone(self.store.get_approved("show files", "linux", "shell"))
        ReviewQueue(self.store).approve(entry, "reviewed")
        self.assertEqual(self.store.get_approved("show files", "linux").implementation, "ls")

    def test_rejected_candidate_is_not_returned(self):
        entry = self.store.add_candidate("show files", "linux", "ls")
        ReviewQueue(self.store).reject(entry, "bad")
        self.assertIsNone(self.store.get_approved("show files", "linux"))

    def test_dangerous_history_prevents_lookup_even_after_sme_approval(self):
        self.store.record_operator_feedback("show files", "linux", "ls", "dangerous")
        entry = self.store.entries[0]
        ReviewQueue(self.store).approve(entry)
        self.assertIsNone(self.store.get_approved("show files", "linux"))

    def test_environments_are_isolated(self):
        linux = self.store.add_candidate("show ports", "linux", "ss -tulpn")
        windows = self.store.add_candidate("show ports", "windows", "netstat -ano")
        queue = ReviewQueue(self.store)
        queue.approve(linux)
        queue.approve(windows)
        self.assertEqual(self.store.get_approved("show ports", "linux").implementation, "ss -tulpn")
        self.assertEqual(self.store.get_approved("show ports", "windows").implementation, "netstat -ano")

    def test_conflict_resolution_uses_highest_approved_score(self):
        first = self.store.add_candidate("list files", "linux", "ls")
        second = self.store.add_candidate("list files", "linux", "find . -maxdepth 1")
        self.store.record_trainer_grade(first.intent, first.environment, first.implementation, 3)
        self.store.record_trainer_grade(second.intent, second.environment, second.implementation, 5)
        ReviewQueue(self.store).approve(first)
        ReviewQueue(self.store).approve(second)
        self.assertEqual(self.store.get_approved("list files", "linux").implementation, "find . -maxdepth 1")

    def test_stats_report_status_buckets(self):
        pending = self.store.add_candidate("one", "local", "cmd1")
        rejected = self.store.add_candidate("two", "local", "cmd2")
        ReviewQueue(self.store).reject(rejected)
        stats = self.store.stats()
        self.assertEqual((stats["total_entries"], stats["pending_review"], stats["rejected_entries"]), (2, 1, 1))

    def test_persistence_round_trip(self):
        self.store.add_candidate("show tables", "postgres", "SELECT 1", "postgres")
        reloaded = KnowledgeBase(self.root / "knowledge.json")
        self.assertEqual(reloaded.entries[0].type, "postgres")

    def test_migration_preserves_feedback_and_marks_imports_pending(self):
        cache = self.root / "command_cache.json"
        cache.write_text(json.dumps({"entries": [{"intent": "files", "command": "ls", "status": "verified"}]}))
        feedback = self.root / "feedback.jsonl"
        feedback.write_text(json.dumps({"intent": "files", "command": "ls", "result": "success"}) + "\n")
        result = migrate_legacy_data(self.store, cache, feedback)
        self.assertEqual(result["imported_feedback"], 1)
        entry = self.store.entries[0]
        self.assertEqual(entry.success_count, 1)
        self.assertFalse(entry.sme_approved)
        self.assertEqual(len(entry.source_history), 1)
        again = migrate_legacy_data(self.store, cache, feedback)
        self.assertEqual(again["already_migrated"], 1)
        self.assertEqual(len(self.store.entries), 1)

    def test_migration_imports_cache_status_when_feedback_absent(self):
        cache = self.root / "cache.json"
        cache.write_text(json.dumps({"entries": [{"intent": "files", "command": "ls", "status": "dangerous"}]}))
        migrate_legacy_data(self.store, cache, self.root / "missing.jsonl")
        self.assertEqual(self.store.entries[0].dangerous_count, 1)

    def test_rbac_learning_permissions(self):
        rbac = RbacEngine()
        self.assertTrue(rbac.authorize_learning(UserContext("op", Role.OPERATOR), "feedback"))
        self.assertFalse(rbac.authorize_learning(UserContext("op", Role.OPERATOR), "grade"))
        self.assertTrue(rbac.authorize_learning(UserContext("trainer", Role.TRAINER), "grade"))
        self.assertFalse(rbac.authorize_learning(UserContext("trainer", Role.TRAINER), "approve"))
        self.assertTrue(rbac.authorize_learning(UserContext("sme", Role.SME), "approve"))


if __name__ == "__main__":
    unittest.main()
