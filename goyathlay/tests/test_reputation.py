import tempfile
import unittest
from pathlib import Path

from goyathlay.feedback import FeedbackResult, FeedbackStore
from goyathlay.reputation import ReputationEngine


class ReputationEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = FeedbackStore(Path(self.temp_dir.name) / "feedback.jsonl")
        self.engine = ReputationEngine(self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_unknown_command_returns_none(self):
        self.assertIsNone(self.engine.get_reputation("unknown command"))

    def test_success_scoring(self):
        self.assertEqual(self.engine.calculate_score(1, 0, 0), 60.0)

    def test_failure_scoring(self):
        self.assertEqual(self.engine.calculate_score(0, 1, 0), 45.0)

    def test_dangerous_scoring(self):
        self.assertEqual(self.engine.calculate_score(0, 0, 1), 25.0)

    def test_mixed_feedback_scoring_and_counts(self):
        self.store.append("intent", "netstat -tuln", FeedbackResult.SUCCESS)
        self.store.append("intent", "netstat -tuln", FeedbackResult.FAILURE)
        self.store.append("intent", "netstat -tuln", FeedbackResult.DANGEROUS)
        self.store.append("intent", "netstat -tuln", FeedbackResult.SKIPPED)

        reputation = self.engine.get_reputation("netstat -tuln")

        self.assertEqual(reputation.success_count, 1)
        self.assertEqual(reputation.failure_count, 1)
        self.assertEqual(reputation.dangerous_count, 1)
        self.assertEqual(reputation.score, 30.0)

    def test_score_clamps_at_high_bound(self):
        self.assertEqual(self.engine.calculate_score(10, 0, 0), 100.0)

    def test_score_clamps_at_low_bound(self):
        self.assertEqual(self.engine.calculate_score(0, 0, 2), 0.0)

    def test_command_matching_is_case_sensitive(self):
        self.store.append("intent", "Netstat -tuln", FeedbackResult.SUCCESS)

        self.assertIsNone(self.engine.get_reputation("netstat -tuln"))

    def test_loads_and_aggregates_multiple_feedback_records(self):
        self.store.append("one", "pwd", FeedbackResult.SUCCESS)
        self.store.append("two", "pwd", FeedbackResult.SUCCESS)
        self.store.append("three", "pwd", FeedbackResult.SUCCESS)

        reputation = self.engine.get_reputation("pwd")

        self.assertEqual(reputation.success_count, 3)
        self.assertEqual(reputation.score, 80.0)


if __name__ == "__main__":
    unittest.main()
