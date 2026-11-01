"""Actionable, stack-trace-free local engine diagnostics."""

from __future__ import annotations


def render_engine_diagnostic(error: object, *, model: str) -> str:
    """Map known local Ollama failures to concise reasons and repair commands."""
    message = str(error).casefold()
    if (
        "no module named 'ollama'" in message
        or "python package is not installed" in message
        or "python package missing" in message
    ):
        reason = "Ollama Python package missing"
        fix = "python3 scripts/install_goyathlay.py"
    elif "daemon is not running" in message or "unreachable" in message or "connection refused" in message:
        reason = "Ollama daemon is not running"
        fix = "ollama serve"
    elif "model" in message and ("not found" in message or "pull it" in message):
        reason = f"Ollama model {model} is missing"
        fix = f"ollama pull {model}"
    else:
        reason = "Local Ollama engine is unavailable"
        fix = "Check that Ollama is running and the configured model is installed."
    return "\n".join(("Engine Status: WARNING", f"Reason: {reason}", "Suggested Fix:", fix))
