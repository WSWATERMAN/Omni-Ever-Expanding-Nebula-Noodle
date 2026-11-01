"""Tests for local Ollama model selection without network calls."""

import unittest
import importlib
import sys
from unittest.mock import patch


class OllamaProviderTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(sys.modules, {"ollama": object()}):
            self.provider_class = importlib.import_module(
                "goyathlay.providers.ollama_provider"
            ).OllamaProvider

    def test_default_model_is_local_coder_model(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(self.provider_class().model, "qwen2.5-coder:14b")

    def test_model_can_be_selected_with_local_environment_setting(self):
        with patch.dict("os.environ", {"GOYATHLAY_OLLAMA_MODEL": "qwen2.5-coder:7b"}):
            self.assertEqual(self.provider_class().model, "qwen2.5-coder:7b")

    def test_explicit_model_takes_precedence(self):
        with patch.dict("os.environ", {"GOYATHLAY_OLLAMA_MODEL": "qwen2.5-coder:7b"}):
            self.assertEqual(self.provider_class("custom-local-model").model, "custom-local-model")


if __name__ == "__main__":
    unittest.main()
