"""Tests for command blocklist matching and persistence."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from goyathlay.blocklist import BlockDecision, CommandBlocklist


class CommandBlocklistTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / ".goyathlay" / "blocklist.json"
        self.blocklist = CommandBlocklist(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_rules_are_created_with_private_permissions(self):
        self.assertEqual(
            self.blocklist.list_commands(),
            ["rm -rf /", "mkfs", ":(){ :|:& };:", "dd if="],
        )
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.path.parent).st_mode & 0o777, 0o700)

    def test_exact_match(self):
        self.assertTrue(self.blocklist.is_blocked("rm -rf /"))
        self.assertEqual(self.blocklist.blocked_by("rm -rf /"), "rm -rf /")

    def test_prefix_match_only_when_rule_ends_in_wildcard(self):
        self.blocklist.add("rm -rf *")

        self.assertTrue(self.blocklist.is_blocked("rm -rf /tmp"))
        self.assertTrue(self.blocklist.is_blocked("rm -rf /var/log"))
        self.assertEqual(self.blocklist.blocked_by("rm -rf /tmp"), "rm -rf *")

    def test_exact_rule_does_not_match_a_longer_command(self):
        self.assertFalse(self.blocklist.is_blocked("rm -rf /tmp"))
        self.assertFalse(self.blocklist.is_blocked("mkfs.ext4 /dev/sda"))

    def test_prefix_does_not_match_similar_word_without_required_separator(self):
        self.blocklist.add("rm -rf *")

        self.assertFalse(self.blocklist.is_blocked("rm -rfish /tmp"))

    def test_add_rule_and_avoid_duplicate(self):
        self.assertTrue(self.blocklist.add("shutdown now"))
        self.assertFalse(self.blocklist.add("shutdown now"))
        self.assertIn("shutdown now", self.blocklist.list_commands())

    def test_remove_rule(self):
        self.blocklist.add("shutdown now")

        self.assertTrue(self.blocklist.remove("shutdown now"))
        self.assertFalse(self.blocklist.remove("shutdown now"))

    def test_persistence(self):
        self.blocklist.add("rm -rf *")
        reloaded = CommandBlocklist(self.path)

        self.assertIn("rm -rf *", reloaded.list_commands())
        self.assertEqual(json.loads(self.path.read_text())["commands"][-1], "rm -rf *")

    def test_decision_reports_blocked_and_allowed_commands(self):
        self.blocklist.add("shutdown*")

        self.assertIs(self.blocklist.decision("shutdown now"), BlockDecision.BLOCK)
        self.assertIs(self.blocklist.decision("pwd"), BlockDecision.ALLOW)

    def test_invalid_rules_are_rejected(self):
        with self.assertRaises(ValueError):
            self.blocklist.add(" ")
        with self.assertRaises(ValueError):
            self.blocklist.add("rm * -rf")


if __name__ == "__main__":
    unittest.main()
