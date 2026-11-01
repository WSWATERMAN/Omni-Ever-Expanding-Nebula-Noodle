"""Tests for the terminal operator console presentation layer."""

import tempfile
import unittest
from pathlib import Path

from goyathlay.profiles import ProfileManager
from goyathlay.ui.banner import render_banner
from goyathlay.ui.hotkeys import ConsoleState, HotkeyManager
from goyathlay.ui.prompt import render_prompt
from goyathlay.ui.statusbar import StatusBar, render_status_output
from goyathlay.ui.views import render_database_plan, render_execution_plan


class OperatorConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.profile_manager = ProfileManager(Path(self.temp_dir.name) / "profiles.json")
        self.profile = self.profile_manager.get_default_profile()
        self.state = ConsoleState(
            profile_manager=self.profile_manager,
            current_profile=self.profile,
            profile_names=[profile.name for profile in self.profile_manager.list_profiles()],
            engine="qwen2.5-coder:7b",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_startup_banner(self):
        banner = render_banner(engine="qwen2.5-coder:7b", profile="production", role="ADMIN")
        self.assertIn("Goyathlay - Autonomous Operations Platform", banner)
        self.assertIn("[Ctrl+B] Cache Bypass", banner)
        self.assertIn("[Ctrl+H] Help", banner)
        self.assertIn("TOFU: Enabled", banner)

    def test_prompt_rendering_and_profile_update(self):
        self.assertEqual(render_prompt("production"), "goyathlay(production) ▷▶ ")
        self.state.cycle_profile()
        self.assertEqual(self.state.profile_name(), "emergency")

    def test_hotkey_toggles_and_profile_switch(self):
        manager = HotkeyManager(self.state)
        self.assertEqual(manager.handle_hotkey("Ctrl+B"), "Cache Bypass Enabled")
        self.assertTrue(self.state.cache_bypass)
        self.assertEqual(manager.handle_hotkey("Ctrl+B"), "Cache Bypass Disabled")
        self.assertEqual(manager.handle_hotkey("Ctrl+K"), "AI Generation Bypass Enabled")
        manager.handle_hotkey("Ctrl+R")
        self.assertFalse(self.state.show_risk)
        manager.handle_hotkey("Ctrl+T")
        self.assertTrue(self.state.show_audit_details)
        manager.handle_hotkey("Ctrl+P")
        self.assertEqual(self.state.profile_name(), "emergency")

    def test_status_output(self):
        text = render_status_output(
            engine="qwen2.5-coder:7b", profile="production", role="ADMIN",
            cache_enabled=True, audit_enabled=True, tofu_enabled=True,
            hosts=12, groups=4, profiles=4,
        )
        self.assertIn("Hosts:          12", text)
        self.assertIn("Groups:         4", text)
        self.assertIn("Version:        1.0.0", text)
        self.assertIn("python3 -m unittest", text)

    def test_execution_plan_rendering(self):
        text = render_execution_plan(
            intent="show listening ports", command="ss -tulpn", targets=["server01"],
            engine="qwen2.5-coder:7b", profile="production", role="ADMIN",
            risk="LOW", reasons=["No known risky patterns detected."],
            reputation=95, policy="ALLOW",
        )
        for expected in ("EXECUTION PLAN", "Intent:\nshow listening ports", "Command:\nss -tulpn",
                         "server01", "Profile:\nproduction", "Role:\nADMIN", "Risk:\nLOW",
                         "Reputation:\n95", "Policy:\nALLOW"):
            self.assertIn(expected, text)

    def test_database_plan_rendering(self):
        text = render_database_plan(
            engine="PostgreSQL", profile="prod", sql="SELECT 1;", risk="LOW", validation="PASSED"
        )
        self.assertIn("DATABASE PLAN", text)
        self.assertIn("Engine:\nPostgreSQL", text)
        self.assertIn("Generated SQL:\nSELECT 1;", text)
        self.assertIn("Validation:\nPASSED", text)

    def test_statusbar_updates_when_state_changes(self):
        statusbar = StatusBar(self.state)
        first = statusbar.render()
        self.assertIn("PROFILE:production", first)
        HotkeyManager(self.state).handle_hotkey("Ctrl+B")
        self.state.cycle_profile()
        second = statusbar.render()
        self.assertIn("PROFILE:emergency", second)
        self.assertIn("CACHE:BYPASS", second)


if __name__ == "__main__":
    unittest.main()
