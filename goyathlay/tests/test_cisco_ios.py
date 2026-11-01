"""Tests for deterministic Cisco IOS intent translation."""

import unittest

from goyathlay.network.cisco_ios import CiscoIOSInterpreter, UnsupportedNetworkIntentError


class CiscoIOSInterpreterTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = CiscoIOSInterpreter()

    def test_supported_show_commands_are_read_only_and_low_risk(self):
        expected = {
            "show interface status": "show interface status",
            "show version": "show version",
            "show inventory": "show inventory",
            "show bgp summary": "show ip bgp summary",
            "show ip route": "show ip route",
            "show spanning-tree": "show spanning-tree",
            "show running-config": "show running-config",
        }
        for intent, command in expected.items():
            with self.subTest(intent=intent):
                result = self.interpreter.translate(intent)
                self.assertEqual(result.command, command)
                self.assertTrue(result.read_only)
                self.assertEqual(result.risk, "LOW")

    def test_unsupported_intent_is_rejected(self):
        with self.assertRaises(UnsupportedNetworkIntentError):
            self.interpreter.translate("configure terminal")

    def test_configuration_is_high_risk_and_show_is_low(self):
        self.assertEqual(self.interpreter.classify("configure terminal"), "HIGH")
        self.assertEqual(self.interpreter.classify("interface Gi0/1"), "HIGH")
        self.assertEqual(self.interpreter.classify("show version"), "LOW")


if __name__ == "__main__":
    unittest.main()
