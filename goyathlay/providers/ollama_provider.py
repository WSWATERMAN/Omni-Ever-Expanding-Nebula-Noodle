import importlib
import os
from typing import Any

from .base import AIProvider
from ..command_cleaner import clean_command


class OllamaProviderError(RuntimeError):
    """Raised with setup guidance when local Ollama is unavailable."""


_INSTALL_GUIDANCE = "Ollama Python package is not installed.\nRun:\npip install ollama"


def ollama_package_error() -> str | None:
    """Return actionable package guidance, or None when the SDK imports."""
    try:
        importlib.import_module("ollama")
    except ImportError:
        return _INSTALL_GUIDANCE
    return None


class OllamaProvider(AIProvider):

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("GOYATHLAY_OLLAMA_MODEL", "qwen2.5-coder:14b")
        self._ollama: Any | None = None

    def validate_setup(self) -> Any:
        """Verify the Python SDK, local daemon, and configured model are ready."""
        if self._ollama is None:
            try:
                self._ollama = importlib.import_module("ollama")
            except ImportError as exc:
                raise OllamaProviderError(_INSTALL_GUIDANCE) from exc
        try:
            response = self._ollama.list()
        except Exception as exc:
            raise OllamaProviderError(
                "Ollama daemon is not running or is unreachable.\n"
                "Start Ollama (for example, run `ollama serve`) and check its local endpoint."
            ) from exc

        records = response.get("models", []) if isinstance(response, dict) else getattr(response, "models", [])
        available = set()
        for record in records or []:
            if isinstance(record, dict):
                name = record.get("model") or record.get("name")
            else:
                name = getattr(record, "model", None) or getattr(record, "name", None)
            if isinstance(name, str):
                available.add(name)
        if self.model not in available:
            raise OllamaProviderError(
                f"Model {self.model} not found in the local Ollama daemon.\n"
                f"Pull it with: ollama pull {self.model}"
            )
        return self._ollama

    def generate_command(self, prompt: str) -> str:
        """Generate a shell command after confirming local Ollama readiness."""
        ollama = self.validate_setup()
        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """
You are Goyathlay.

Return ONE shell command.

Rules:
- No markdown
- No comments
- No explanations
- Return only the command
"""
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            )
            return clean_command(response["message"]["content"])
        except Exception as exc:
            raise OllamaProviderError(
                "Ollama command generation failed. Check that the local daemon is still running "
                "and the selected model is available."
            ) from exc
