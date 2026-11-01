"""Tests for private local host inventory persistence and resolution."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from goyathlay.inventory import HostInventory, HostRecord, InventoryError


class HostInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / ".goyathlay" / "inventory.json"
        self.inventory = HostInventory(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def host(self, name="server01"):
        return HostRecord(name, f"{name}.example", 22, "ubuntu")

    def test_add_get_list_and_remove_host(self):
        record = self.host()
        self.inventory.add_host(record)

        self.assertEqual(self.inventory.get_host("server01"), record)
        self.assertEqual(self.inventory.list_hosts(), [record])
        self.assertTrue(self.inventory.remove_host("server01"))
        self.assertIsNone(self.inventory.get_host("server01"))
        self.assertFalse(self.inventory.remove_host("server01"))

    def test_add_remove_and_list_group(self):
        self.inventory.add_host(self.host())
        self.inventory.add_host(self.host("server02"))
        self.inventory.add_group("prod", ["server01", "server02"])

        self.assertEqual(self.inventory.get_group("prod"), ["server01", "server02"])
        self.assertEqual(self.inventory.list_groups(), {"prod": ["server01", "server02"]})
        self.assertTrue(self.inventory.remove_group("prod"))
        self.assertIsNone(self.inventory.get_group("prod"))

    def test_remove_host_cleans_group_memberships(self):
        self.inventory.add_host(self.host())
        self.inventory.add_group("prod", ["server01"])

        self.inventory.remove_host("server01")

        self.assertEqual(self.inventory.get_group("prod"), [])

    def test_resolves_host_and_group_to_host_records(self):
        first = self.host()
        second = self.host("server02")
        self.inventory.add_host(first)
        self.inventory.add_host(second)
        self.inventory.add_group("prod", ["server01", "server02"])

        self.assertEqual(self.inventory.resolve_target("server01"), [first])
        self.assertEqual(self.inventory.resolve_target("prod"), [first, second])

    def test_unknown_group_member_is_rejected(self):
        with self.assertRaisesRegex(InventoryError, "Unknown host"):
            self.inventory.add_group("prod", ["missing"])

    def test_duplicate_host_and_cross_namespace_names_are_rejected(self):
        self.inventory.add_host(self.host())
        with self.assertRaisesRegex(InventoryError, "already exists"):
            self.inventory.add_host(self.host())
        with self.assertRaisesRegex(InventoryError, "already exists"):
            self.inventory.add_group("server01", [])

    def test_duplicate_group_name_is_rejected(self):
        self.inventory.add_group("prod", [])
        with self.assertRaisesRegex(InventoryError, "already exists"):
            self.inventory.add_group("prod", [])

    def test_persistence_preserves_hosts_and_groups(self):
        self.inventory.add_host(self.host())
        self.inventory.add_host(self.host("server02"))
        self.inventory.add_group("prod", ["server01", "server02"])

        loaded = HostInventory(self.path)

        self.assertEqual(loaded.resolve_target("prod"), [self.host(), self.host("server02")])

    def test_creates_owner_only_storage(self):
        self.inventory.add_host(self.host())

        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.path.parent).st_mode & 0o777, 0o700)
        self.assertEqual(json.loads(self.path.read_text())["hosts"]["server01"]["username"], "ubuntu")

    def test_invalid_group_reference_in_file_fails_closed(self):
        self.path.write_text(
            json.dumps({"hosts": {}, "groups": {"prod": ["missing"]}}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(InventoryError, "unknown host reference"):
            HostInventory(self.path)

    def test_host_record_validates_fields(self):
        with self.assertRaises(ValueError):
            HostRecord("server", "server.example", 70000, "ubuntu")


if __name__ == "__main__":
    unittest.main()
