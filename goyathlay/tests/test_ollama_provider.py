"""Tests for local Ollama model selection without network calls."""

import unittest
import importlib
import sys
from unittest.mock import Mock, patch


class OllamaProviderTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(sys.modules, {"ollama": object()}):
            self.provider_module = importlib.import_module("goyathlay.providers.ollama_provider")
        self.provider_class = self.provider_module.OllamaProvider

    def test_default_model_is_local_coder_model(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(self.provider_class().model, "qwen2.5-coder:14b")

    def test_model_can_be_selected_with_local_environment_setting(self):
        with patch.dict("os.environ", {"GOYATHLAY_OLLAMA_MODEL": "qwen2.5-coder:7b"}):
            self.assertEqual(self.provider_class().model, "qwen2.5-coder:7b")

    def test_explicit_model_takes_precedence(self):
        with patch.dict("os.environ", {"GOYATHLAY_OLLAMA_MODEL": "qwen2.5-coder:7b"}):
            self.assertEqual(self.provider_class("custom-local-model").model, "custom-local-model")

    def test_dependency_detection_reports_missing_package(self):
        with patch.object(self.provider_module.importlib, "import_module", side_effect=ImportError):
            message = self.provider_module.ollama_package_error()
        self.assertIn("Ollama Python package is not installed", message)
        self.assertIn("pip install ollama", message)

    def test_provider_missing_package_has_actionable_error(self):
        provider = self.provider_class("local-model")
        with patch.object(self.provider_module.importlib, "import_module", side_effect=ImportError):
            with self.assertRaisesRegex(self.provider_module.OllamaProviderError, "pip install ollama"):
                provider.validate_setup()

    def test_provider_reports_unreachable_daemon(self):
        provider = self.provider_class("local-model")
        fake_ollama = Mock()
        fake_ollama.list.side_effect = ConnectionError("offline")
        with patch.object(self.provider_module.importlib, "import_module", return_value=fake_ollama):
            with self.assertRaisesRegex(self.provider_module.OllamaProviderError, "daemon is not running"):
                provider.validate_setup()

    def test_provider_reports_missing_model_with_pull_command(self):
        provider = self.provider_class("qwen2.5-coder:7b")
        fake_ollama = Mock()
        fake_ollama.list.return_value = {"models": [{"model": "qwen2.5:1.5b"}]}
        with patch.object(self.provider_module.importlib, "import_module", return_value=fake_ollama):
            with self.assertRaisesRegex(self.provider_module.OllamaProviderError, "ollama pull qwen2.5-coder:7b"):
                provider.validate_setup()

    def test_provider_accepts_installed_model_and_generates(self):
        provider = self.provider_class("qwen2.5-coder:7b")
        fake_ollama = Mock()
        fake_ollama.list.return_value = {"models": [{"model": "qwen2.5-coder:7b"}]}
        fake_ollama.chat.return_value = {"message": {"content": "```bash\nss -tulpn\n```"}}
        with patch.object(self.provider_module.importlib, "import_module", return_value=fake_ollama):
            self.assertEqual(provider.generate_command("show listening ports"), "ss -tulpn")


if __name__ == "__main__":
    unittest.main()
