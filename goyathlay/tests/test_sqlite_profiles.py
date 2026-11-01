"""Tests for secure SQLite database profile persistence."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from goyathlay.db.sqlite_profiles import (
    SqliteProfile,
    SqliteProfileManager,
    SqliteProfileNotFoundError,
)


class SqliteProfileManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / ".goyathlay" / "sqlite_profiles.json"
        self.manager = SqliteProfileManager(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_profile_and_get_default(self):
        profile = SqliteProfile("local", "/opt/app/data/app.db")

        self.manager.add_profile(profile)

        self.assertEqual(self.manager.get_default_profile(), profile)
        self.assertEqual(self.manager.load_profile("local"), profile)
        self.assertEqual(self.manager.list_profiles(), [profile])

    def test_remove_profile(self):
        self.manager.add_profile(SqliteProfile("local", "/tmp/app.db"))

        self.assertTrue(self.manager.remove_profile("local"))
        self.assertFalse(self.manager.remove_profile("local"))
        with self.assertRaises(SqliteProfileNotFoundError):
            self.manager.get_default_profile()

    def test_missing_profile_raises(self):
        with self.assertRaises(SqliteProfileNotFoundError):
            self.manager.load_profile("missing")
        with self.assertRaises(SqliteProfileNotFoundError):
            self.manager.get_default_profile()

    def test_set_default_and_profile_records_persist(self):
        first = SqliteProfile("local", "/tmp/local.db")
        second = SqliteProfile("test", "/tmp/test.db")
        self.manager.add_profile(first)
        self.manager.add_profile(second)
        self.manager.set_default_profile("test")

        reloaded = SqliteProfileManager(self.path)
        self.assertEqual(reloaded.get_default_profile(), second)
        self.assertEqual({item.name for item in reloaded.list_profiles()}, {"local", "test"})

    def test_file_and_directory_permissions_are_private(self):
        self.manager.add_profile(SqliteProfile("local", "/tmp/app.db"))

        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(json.loads(self.path.read_text())["default"], "local")


if __name__ == "__main__":
    unittest.main()
