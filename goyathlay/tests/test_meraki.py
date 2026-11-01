"""Tests for declarative, read-only Meraki operation mapping."""

import unittest

from goyathlay.network.meraki import MerakiInterpreter, UnsupportedMerakiIntentError


class MerakiInterpreterTests(unittest.TestCase):
    def test_supported_intents_map_to_fixed_get_operations(self):
        interpreter = MerakiInterpreter()
        for intent in ("show appliance status", "show vpn status", "show switch status", "show wireless status"):
            with self.subTest(intent=intent):
                operation = interpreter.translate(intent)
                self.assertEqual(operation.method, "GET")
                self.assertTrue(operation.read_only)
                self.assertEqual(operation.risk, "LOW")
                self.assertTrue(operation.path.startswith("/organizations/"))

    def test_unknown_or_mutating_intent_is_rejected(self):
        with self.assertRaises(UnsupportedMerakiIntentError):
            MerakiInterpreter().translate("delete network")

    def test_translation_has_no_request_side_effects(self):
        operation = MerakiInterpreter().translate("show vpn status")
        self.assertEqual(operation.method, "GET")
        self.assertIn("appliance/vpn/statuses", operation.path)


if __name__ == "__main__":
    unittest.main()
