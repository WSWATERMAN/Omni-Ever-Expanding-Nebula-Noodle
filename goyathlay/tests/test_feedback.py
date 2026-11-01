import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from goyathlay.feedback import FeedbackManager, FeedbackResult, FeedbackStore


class FeedbackManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / ".goyathlay" / "feedback.jsonl"
        self.store = FeedbackStore(self.path)
        self.manager = FeedbackManager(self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def assert_review_persists(self, answer, expected):
        with patch("builtins.input", return_value=answer):
            result = self.manager.review("show listening ports", "netstat -tuln")

        self.assertEqual(result, expected)
        records = self.store.load_history()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["intent"], "show listening ports")
        self.assertEqual(records[0]["command"], "netstat -tuln")
        self.assertEqual(records[0]["result"], expected.value)
        self.assertTrue(records[0]["timestamp"].endswith("Z"))

    def test_success_feedback_is_stored(self):
        self.assert_review_persists("Y", FeedbackResult.SUCCESS)

    def test_failure_feedback_is_stored(self):
        self.assert_review_persists("N", FeedbackResult.FAILURE)

    def test_dangerous_feedback_is_stored(self):
        self.assert_review_persists("D", FeedbackResult.DANGEROUS)

    def test_skipped_feedback_is_stored(self):
        self.assert_review_persists("S", FeedbackResult.SKIPPED)

    def test_invalid_input_repeats_until_valid(self):
        with patch("builtins.input", side_effect=["banana", "yes"]) as mocked_input:
            result = self.manager.review("list files", "ls -la")

        self.assertEqual(result, FeedbackResult.SUCCESS)
        self.assertEqual(mocked_input.call_count, 2)
        self.assertEqual(self.store.load_history()[0]["result"], "success")

    def test_load_preserves_all_appended_records(self):
        self.store.append("intent one", "command one", FeedbackResult.SUCCESS)
        self.store.append("intent two", "command two", FeedbackResult.DANGEROUS)
        reloaded = FeedbackStore(self.path)

        history = reloaded.load_history()
        self.assertEqual(len(history), 2)
        self.assertEqual([record["intent"] for record in history], ["intent one", "intent two"])
        self.assertEqual(len(self.path.read_text().splitlines()), 2)

    def test_operator_view_does_not_show_implementation(self):
        output = io.StringIO()
        with patch("builtins.input", return_value="Y"), redirect_stdout(output):
            self.manager.review("show files", "ls -la", operator_view=True)
        self.assertIn("Was this result acceptable?", output.getvalue())
        self.assertNotIn("ls -la", output.getvalue())


if __name__ == "__main__":
    unittest.main()
