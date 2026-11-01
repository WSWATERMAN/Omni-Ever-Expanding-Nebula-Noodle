"""Tests for safe Aruba command translation."""

import unittest

from goyathlay.network.aruba import ArubaInterpreter
from goyathlay.network.cisco_ios import UnsupportedNetworkIntentError


class ArubaInterpreterTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = ArubaInterpreter()

    def test_supported_intents_are_read_only(self):
        for intent in (
            "show version", "show system status", "show interface status", "show interfaces",
            "show vlans", "show ip route", "show running-config", "show spanning-tree",
        ):
            with self.subTest(intent=intent):
                result = self.interpreter.translate(intent)
                self.assertEqual(result.vendor, "aruba")
                self.assertTrue(result.read_only)
                self.assertEqual(result.risk, "LOW")
                self.assertTrue(result.command.startswith("show "))

    def test_unknown_intent_is_rejected(self):
        with self.assertRaises(UnsupportedNetworkIntentError):
            self.interpreter.translate("configure terminal")

    def test_non_show_command_is_high_risk(self):
        self.assertEqual(self.interpreter.classify("configure terminal"), "HIGH")


if __name__ == "__main__":
    unittest.main()
