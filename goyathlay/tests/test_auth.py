"""Tests for local PBKDF2 authentication storage."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from goyathlay.auth import AuthError, AuthManager
from goyathlay.rbac import Role, UserContext


class AuthManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / ".goyathlay" / "users.json"
        self.manager = AuthManager(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_creates_account_with_hash_and_authenticates(self):
        user = self.manager.create_user("scott", Role.OPERATOR, "Correct Horse 42!")
        self.assertEqual(user, UserContext("scott", Role.OPERATOR))
        self.assertEqual(self.manager.authenticate("scott", "Correct Horse 42!"), user)
        stored = self.path.read_text()
        self.assertNotIn("Correct Horse", stored)
        self.assertIn("pbkdf2_sha256", stored)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.path.parent).st_mode & 0o777, 0o700)

    def test_wrong_or_unknown_credentials_return_none(self):
        self.manager.create_user("local", Role.ADMIN, "correct horse battery")
        self.assertIsNone(self.manager.authenticate("local", "incorrect password"))
        self.assertIsNone(self.manager.authenticate("unknown", "incorrect password"))

    def test_duplicate_and_weak_password_rejected(self):
        self.manager.create_user("local", Role.ADMIN, "correct horse battery")
        with self.assertRaises(AuthError):
            self.manager.create_user("local", Role.VIEWER, "another valid password")
        with self.assertRaises(ValueError):
            self.manager.create_user("other", Role.VIEWER, "short")

    def test_user_listing_omits_hashes_and_persists(self):
        self.manager.create_user("local", Role.ADMIN, "correct horse battery")
        reloaded = AuthManager(self.path)
        self.assertEqual(reloaded.list_users(), [UserContext("local", Role.ADMIN)])
        self.assertEqual(set(json.loads(self.path.read_text())), {"users"})


if __name__ == "__main__":
    unittest.main()
