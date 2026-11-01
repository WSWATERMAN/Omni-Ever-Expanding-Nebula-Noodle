"""Tests for secure local policy profile persistence."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from goyathlay.profiles import (
    PolicyProfile,
    ProfileManager,
    ProfileNotFoundError,
)
from goyathlay.policy import PolicyDecision, PolicyEngine
from goyathlay.risk import RiskLevel


class ProfileManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / ".goyathlay" / "profiles.json"
        self.manager = ProfileManager(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_default_config(self):
        self.assertTrue(self.path.exists())
        self.assertEqual(self.manager.get_default_profile(), PolicyProfile("production", False, False, 50))
        self.assertEqual(
            {profile.name for profile in self.manager.list_profiles()},
            {"development", "staging", "production", "emergency"},
        )
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        config = json.loads(self.path.read_text())
        self.assertEqual(config["default"], "production")
        self.assertEqual(
            set(config["profiles"]["production"]),
            {"allow_high_risk", "allow_override", "minimum_reputation"},
        )

    def test_load_profile(self):
        self.assertEqual(self.manager.load_profile("staging"), PolicyProfile("staging", True, True, 25))

    def test_missing_profile_raises(self):
        with self.assertRaises(ProfileNotFoundError):
            self.manager.load_profile("unknown")

    def test_profile_switching_persists_default(self):
        self.manager.set_default_profile("development")

        reloaded = ProfileManager(self.path)

        self.assertEqual(reloaded.get_default_profile().name, "development")
        self.assertEqual(json.loads(self.path.read_text())["default"], "development")

    def test_default_profile_persistence(self):
        self.manager.set_default_profile("emergency")

        self.assertEqual(ProfileManager(self.path).get_default_profile().name, "emergency")

    def test_save_profile_preserves_existing_profiles(self):
        custom = PolicyProfile("qa", True, True, 10)

        self.manager.save_profile(custom)

        self.assertEqual(self.manager.load_profile("qa"), custom)
        self.assertEqual(self.manager.get_default_profile().name, "production")
        self.assertTrue(self.manager.path.exists())

    def test_loads_prior_profile_records_with_embedded_name(self):
        config = json.loads(self.path.read_text())
        for name, values in config["profiles"].items():
            values["name"] = name
        self.path.write_text(json.dumps(config), encoding="utf-8")

        loaded = ProfileManager(self.path)

        self.assertEqual(loaded.get_default_profile().name, "production")
        loaded.set_default_profile("staging")
        self.assertNotIn("name", json.loads(self.path.read_text())["profiles"]["staging"])

    def test_production_denies_high_risk_and_below_minimum_reputation(self):
        engine = PolicyEngine()
        production = self.manager.load_profile("production")

        high = engine.evaluate(RiskLevel.HIGH, 72, production)
        low_reputation = engine.evaluate(RiskLevel.LOW, 49, production)

        self.assertIs(high.decision, PolicyDecision.DENY)
        self.assertIn("Production profile blocks high-risk commands", high.reasons)
        self.assertIs(low_reputation.decision, PolicyDecision.DENY)

    def test_staging_requires_override_for_high_risk_and_low_reputation(self):
        engine = PolicyEngine()
        staging = self.manager.load_profile("staging")

        high = engine.evaluate(RiskLevel.HIGH, 72, staging)
        below_minimum = engine.evaluate(RiskLevel.LOW, 24, staging)

        self.assertIs(high.decision, PolicyDecision.REQUIRE_EXTRA_CONFIRMATION)
        self.assertIs(below_minimum.decision, PolicyDecision.REQUIRE_EXTRA_CONFIRMATION)

    def test_development_and_emergency_allow_every_risk_level(self):
        engine = PolicyEngine()
        for name in ("development", "emergency"):
            profile = self.manager.load_profile(name)
            for risk_level in RiskLevel:
                with self.subTest(profile=name, risk=risk_level):
                    result = engine.evaluate(risk_level, 0, profile)
                    self.assertIs(result.decision, PolicyDecision.ALLOW)


if __name__ == "__main__":
    unittest.main()
