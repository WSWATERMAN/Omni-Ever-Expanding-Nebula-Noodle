"""Tests for maintenance-window storage and enforcement."""

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from goyathlay.maintenance import MaintenanceManager, MaintenanceWindow


class MaintenanceManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / ".goyathlay" / "maintenance.json"
        self.manager = MaintenanceManager(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_has_no_windows_and_allows_execution(self):
        self.assertEqual(json.loads(self.path.read_text()), {"enabled": False, "windows": []})
        self.assertTrue(self.manager.is_allowed("production", datetime(2026, 10, 31, 18, 45)))
        self.assertEqual(os.stat(self.path.parent).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_disabled_window_does_not_restrict(self):
        self.manager.add_window("production", ["SAT", "SUN"], "01:00", "05:00")
        self.assertTrue(self.manager.is_allowed("production", datetime(2026, 10, 31, 18, 45)))

    def test_enabled_matching_window_allows_inside_time(self):
        self.manager.add_window("production", ["SAT", "SUN"], "01:00", "05:00")
        self.manager.set_enabled(True)
        self.assertTrue(self.manager.is_allowed("production", datetime(2026, 10, 31, 3, 0)))

    def test_enabled_matching_window_denies_outside_time(self):
        self.manager.add_window("production", ["SAT", "SUN"], "01:00", "05:00")
        self.manager.set_enabled(True)
        self.assertFalse(self.manager.is_allowed("production", datetime(2026, 10, 31, 5, 0)))

    def test_windows_are_scoped_to_profile(self):
        self.manager.add_window("production", ["SAT"], "01:00", "05:00")
        self.manager.set_enabled(True)
        now = datetime(2026, 10, 31, 3, 0)
        self.assertFalse(self.manager.is_allowed("staging", now))
        self.assertTrue(self.manager.is_allowed("production", now))

    def test_empty_enabled_schedule_allows_per_no_windows_rule(self):
        self.manager.set_enabled(True)
        self.assertTrue(self.manager.is_allowed("production", datetime(2026, 10, 31, 18, 45)))

    def test_add_remove_and_list(self):
        window = MaintenanceWindow("production", ["sat", "sun"], "01:00", "05:00")
        self.assertTrue(self.manager.add_window(window))
        self.assertFalse(self.manager.add_window(window))
        self.assertEqual(self.manager.list_windows(), [MaintenanceWindow("production", ["SAT", "SUN"], "01:00", "05:00")])
        self.assertTrue(self.manager.remove_window("production"))
        self.assertFalse(self.manager.remove_window("production"))
        self.assertEqual(self.manager.list_windows(), [])

    def test_persistence_including_enabled_state(self):
        self.manager.add_window("production", ["SAT", "SUN"], "01:00", "05:00")
        self.manager.set_enabled(True)
        loaded = MaintenanceManager(self.path)
        self.assertTrue(loaded.enabled)
        self.assertEqual(len(loaded.list_windows()), 1)
        self.assertEqual(loaded.list_windows()[0].name, "production")

    def test_overnight_window_spans_into_next_day(self):
        self.manager.add_window("production", ["SAT"], "23:00", "02:00")
        self.manager.set_enabled(True)
        self.assertTrue(self.manager.is_allowed("production", datetime(2026, 11, 1, 1, 0)))
        self.assertFalse(self.manager.is_allowed("production", datetime(2026, 11, 1, 2, 0)))

    def test_invalid_window_is_rejected(self):
        with self.assertRaises(ValueError):
            MaintenanceWindow("production", ["FUNDAY"], "01:00", "05:00")
        with self.assertRaises(ValueError):
            MaintenanceWindow("production", ["SAT"], "1:00", "05:00")


if __name__ == "__main__":
    unittest.main()
