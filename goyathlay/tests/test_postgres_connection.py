"""Tests for local PostgreSQL profiles and connection setup."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from goyathlay.db.connection import PostgresConnectionManager
from goyathlay.db.profiles import (
    DatabaseProfileNotFoundError,
    DbProfile,
)


class PostgresConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / ".goyathlay" / "db_profiles.json"
        self.psycopg = Mock()
        self.connection = Mock()
        self.psycopg.connect.return_value = self.connection
        self.manager = PostgresConnectionManager(self.path, psycopg_module=self.psycopg)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_storage_initializes_private_empty_profile_file(self):
        self.assertEqual(json.loads(self.path.read_text()), {"default": None, "profiles": {}})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)

    def test_load_profile_and_list_profiles(self):
        prod = DbProfile("prod", "db01", 5432, "postgres", "readonly")
        self.manager.add_profile(prod, make_default=True)

        self.assertEqual(self.manager.load_profile(), prod)
        self.assertEqual(self.manager.load_profile("prod"), prod)
        self.assertEqual(self.manager.list_profiles(), [prod])

    def test_missing_profile_raises(self):
        with self.assertRaises(DatabaseProfileNotFoundError):
            self.manager.load_profile("prod")
        with self.assertRaises(DatabaseProfileNotFoundError):
            self.manager.load_profile()

    def test_default_profile_selection_persists(self):
        dev = DbProfile("dev", "localhost", 5432, "app", "readonly")
        prod = DbProfile("prod", "db01", 5432, "postgres", "readonly")
        self.manager.add_profile(dev)
        self.manager.add_profile(prod)
        self.manager.set_default_profile("prod")

        reloaded = PostgresConnectionManager(self.path, psycopg_module=self.psycopg)
        self.assertEqual(reloaded.load_profile().name, "prod")

    def test_connect_uses_read_only_defaults_without_password_storage(self):
        profile = DbProfile("prod", "db01", 5432, "postgres", "readonly")
        self.manager.add_profile(profile, make_default=True)

        connected = self.manager.connect()

        self.assertIs(connected, self.connection)
        self.assertFalse(self.connection.autocommit)
        self.psycopg.connect.assert_called_once_with(
            host="db01",
            port=5432,
            dbname="postgres",
            user="readonly",
            connect_timeout=5,
            application_name="goyathlay",
            options="-c default_transaction_read_only=on",
        )
        self.assertNotIn("password", self.psycopg.connect.call_args.kwargs)

    def test_connection_errors_are_wrapped(self):
        self.manager.add_profile(DbProfile("prod", "db01", 5432, "postgres", "readonly"), make_default=True)
        self.psycopg.connect.side_effect = OSError("offline")

        with self.assertRaisesRegex(RuntimeError, "Could not connect to PostgreSQL profile"):
            self.manager.connect()


if __name__ == "__main__":
    unittest.main()
