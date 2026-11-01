"""Tests for SQL Server profile storage."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from goyathlay.db.mssql_profiles import (
    MssqlProfile,
    MssqlProfileManager,
    MssqlProfileNotFoundError,
)


class MssqlProfileManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / ".goyathlay" / "mssql_profiles.json"
        self.manager = MssqlProfileManager(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_load_and_default_profile(self):
        profile = MssqlProfile("prod", "sql01", "inventory", "readonly", 1433)
        self.manager.add_profile(profile, make_default=True)

        self.assertEqual(self.manager.load_profile(), profile)
        self.assertEqual(self.manager.load_profile("prod"), profile)
        self.assertEqual(self.manager.get_default_profile(), profile)
        self.assertEqual(self.manager.list_profiles(), [profile])

    def test_remove_profile_and_default(self):
        self.manager.add_profile(MssqlProfile("prod", "sql01", "inventory", "readonly"))

        self.assertTrue(self.manager.remove_profile("prod"))
        self.assertFalse(self.manager.remove_profile("prod"))
        with self.assertRaises(MssqlProfileNotFoundError):
            self.manager.get_default_profile()

    def test_set_default_persists(self):
        self.manager.add_profile(MssqlProfile("dev", "localhost", "app", "reader"))
        self.manager.add_profile(MssqlProfile("prod", "sql01", "app", "reader"))
        self.manager.set_default_profile("prod")
        self.assertEqual(MssqlProfileManager(self.path).get_default_profile().name, "prod")

    def test_permissions_and_password_are_not_stored(self):
        self.manager.add_profile(MssqlProfile("prod", "sql01", "app", "reader"))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        self.assertNotIn("password", json.loads(self.path.read_text())["profiles"]["prod"])

    def test_rejects_connection_string_delimiters_in_profile_fields(self):
        with self.assertRaises(ValueError):
            MssqlProfile("prod", "sql01;TrustServerCertificate=yes", "app", "reader")


if __name__ == "__main__":
    unittest.main()
