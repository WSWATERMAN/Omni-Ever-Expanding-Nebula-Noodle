import tempfile
import unittest
from pathlib import Path

from goyathlay.cache import CachedCommand, CommandCache


class CommandCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / ".goyathlay" / "command_cache.json"
        self.cache = CommandCache(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_record_success_can_be_retrieved(self):
        stored = self.cache.record_success("show listening ports", "netstat -tuln")

        self.assertEqual(stored.status, "verified")
        self.assertEqual(
            self.cache.get_verified("show listening ports"),
            stored,
        )

    def test_record_failure_is_never_returned_as_verified(self):
        self.cache.record_failure("show listening ports", "netstat -tuln")

        self.assertIsNone(self.cache.get_verified("show listening ports"))

    def test_record_dangerous_is_never_returned(self):
        self.cache.record_success("delete temporary files", "rm -rf /tmp/example")
        self.cache.record_dangerous("delete temporary files", "rm -rf /tmp/example")

        self.assertIsNone(self.cache.get_verified("delete temporary files"))

    def test_cache_miss_returns_none(self):
        self.assertIsNone(self.cache.get_verified("unseen intent"))

    def test_persistence_survives_reload(self):
        stored = self.cache.record_success("show listening ports", "netstat -tuln")
        reloaded = CommandCache(self.path)

        self.assertEqual(reloaded.get_verified("show listening ports"), stored)
        self.assertEqual(reloaded.history(), [stored])

    def test_duplicate_consecutive_success_is_ignored(self):
        first = self.cache.record_success("show listening ports", "netstat -tuln")
        second = self.cache.record_success("show listening ports", "netstat -tuln")

        self.assertEqual(first, second)
        self.assertEqual(len(self.cache.history()), 1)

    def test_failure_supersedes_earlier_verified_state_but_preserves_history(self):
        self.cache.record_success("show listening ports", "netstat -tuln")
        self.cache.record_failure("show listening ports", "netstat -tuln")

        self.assertIsNone(self.cache.get_verified("show listening ports"))
        self.assertEqual([entry.status for entry in self.cache.history()], ["verified", "failed"])

    def test_intent_lookup_normalizes_case_and_whitespace(self):
        self.cache.record_success("  Show   Listening Ports ", "netstat -tuln")

        self.assertIsNotNone(self.cache.get_verified("show listening ports"))

    def test_returns_cached_command_model(self):
        cached = CachedCommand("intent", "command", "verified", "2026-10-31T12:00:00Z")

        self.assertEqual(cached.status, "verified")


if __name__ == "__main__":
    unittest.main()
