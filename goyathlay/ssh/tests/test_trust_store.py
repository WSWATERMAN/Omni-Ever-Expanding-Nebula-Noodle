import json
import tempfile
import unittest
from pathlib import Path

from goyathlay.ssh import HostIdentity, TrustStore, TrustStoreError


class TrustStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "trust_store.json"
        self.store = TrustStore(self.path)
        self.identity = HostIdentity("server01", 22, "ssh-ed25519", "SHA256:abc123")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_creates_private_store_and_supports_lookup_and_remove(self):
        self.assertTrue(self.path.exists())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

        self.store.store(self.identity)
        self.assertEqual(self.store.lookup("server01")["fingerprint"], "SHA256:abc123")
        self.assertTrue(self.store.remove("server01"))
        self.assertIsNone(self.store.lookup("server01"))
        self.assertFalse(self.store.remove("server01"))

    def test_nonstandard_ports_have_separate_trust_records(self):
        alternate = HostIdentity("server01", 2222, "ssh-ed25519", "SHA256:other")
        self.store.store(self.identity)
        self.store.store(alternate)

        self.assertEqual(self.store.lookup("server01", 22)["fingerprint"], "SHA256:abc123")
        self.assertEqual(self.store.lookup("server01", 2222)["fingerprint"], "SHA256:other")

    def test_invalid_store_data_fails_closed(self):
        self.path.write_text(json.dumps({"wrong": {}}))

        with self.assertRaisesRegex(TrustStoreError, "hosts"):
            TrustStore(self.path)

    def test_rejects_symbolic_link_store_file(self):
        target = Path(self.temp_dir.name) / "target.json"
        target.write_text('{"hosts": {}}')
        self.path.unlink()
        self.path.symlink_to(target)

        with self.assertRaisesRegex(TrustStoreError, "symbolic links"):
            TrustStore(self.path)


if __name__ == "__main__":
    unittest.main()
