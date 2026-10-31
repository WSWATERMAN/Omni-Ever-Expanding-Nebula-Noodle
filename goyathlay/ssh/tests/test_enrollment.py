import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goyathlay.ssh import EnrollmentManager, EnrollmentResult, HostIdentity, TrustStore


class EnrollmentManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name) / ".goyathlay" / "trust_store.json"
        self.store = TrustStore(self.store_path)
        self.manager = EnrollmentManager(self.store)
        self.identity = HostIdentity(
            host="server01",
            port=22,
            algorithm="ssh-ed25519",
            fingerprint="SHA256:abc123",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("builtins.input", return_value="T")
    def test_unknown_host_is_stored_after_permanent_trust(self, mocked_input):
        result = self.manager.enroll(self.identity)

        self.assertEqual(result, EnrollmentResult.TRUST_PERMANENT)
        mocked_input.assert_called_once()
        data = json.loads(self.store_path.read_text())
        self.assertEqual(data["hosts"]["server01"]["fingerprint"], "SHA256:abc123")
        self.assertEqual(data["hosts"]["server01"]["algorithm"], "ssh-ed25519")
        self.assertTrue(data["hosts"]["server01"]["first_seen"].endswith("Z"))

    @patch("builtins.input", return_value="O")
    def test_one_time_trust_does_not_change_store(self, mocked_input):
        before = self.store_path.read_text()

        result = self.manager.enroll(self.identity)

        self.assertEqual(result, EnrollmentResult.TRUST_ONCE)
        mocked_input.assert_called_once()
        self.assertEqual(self.store_path.read_text(), before)

    def test_matching_known_host_needs_no_prompt(self):
        self.store.store(self.identity)

        with patch("builtins.input", side_effect=AssertionError("should not prompt")) as mocked_input:
            result = self.manager.enroll(self.identity)

        self.assertEqual(result, EnrollmentResult.ALREADY_TRUSTED)
        mocked_input.assert_not_called()

    @patch("builtins.input", return_value="R")
    def test_changed_fingerprint_is_rejected_without_replacement(self, mocked_input):
        self.store.store(self.identity)
        changed = HostIdentity("server01", 22, "ssh-ed25519", "SHA256:changed")

        result = self.manager.enroll(changed)

        self.assertEqual(result, EnrollmentResult.REJECT)
        mocked_input.assert_called_once()
        self.assertEqual(self.store.lookup("server01")["fingerprint"], "SHA256:abc123")

    @patch("builtins.input", return_value="T")
    def test_changed_fingerprint_can_be_replaced_explicitly(self, mocked_input):
        self.store.store(self.identity)
        changed = HostIdentity("server01", 22, "ssh-ed25519", "SHA256:changed")

        result = self.manager.enroll(changed)

        self.assertEqual(result, EnrollmentResult.REPLACED)
        mocked_input.assert_called_once()
        self.assertEqual(self.store.lookup("server01")["fingerprint"], "SHA256:changed")


if __name__ == "__main__":
    unittest.main()
