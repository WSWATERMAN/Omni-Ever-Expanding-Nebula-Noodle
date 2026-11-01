"""Preflight local Ollama and start the Goyathlay operator CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence


DEFAULT_MODEL = "qwen2.5-coder:14b"


def _model_is_listed(output: str, model: str) -> bool:
    """Return whether ``ollama list`` includes the exact model name."""
    return any(row.split() and row.split()[0] == model for row in output.splitlines()[1:])


def verify_model(
    *,
    model: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
    input_fn: Callable[[str], str] = input,
    emit: Callable[[str], None] = print,
    heal_auto: bool = False,
    interactive: bool | None = None,
) -> bool:
    """Check local Ollama and the selected model, optionally pulling it by consent."""
    selected_model = model or os.environ.get("GOYATHLAY_OLLAMA_MODEL") or DEFAULT_MODEL
    if not selected_model.strip() or any(char.isspace() for char in selected_model):
        emit("Invalid configured Ollama model name.")
        return False

    ollama = which("ollama")
    if not ollama:
        emit("Ollama is not installed. Install Ollama, then run this launcher again.")
        return False

    def list_models() -> subprocess.CompletedProcess[str] | None:
        try:
            result = runner([ollama, "list"], capture_output=True, text=True, check=False, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result if result.returncode == 0 else None

    listing = list_models()
    if listing is None:
        emit("Ollama service is unavailable.\nStart it:\nollama serve")
        return False
    if _model_is_listed(listing.stdout or "", selected_model):
        emit(f"Ollama model verified: {selected_model}")
        return True

    def explain_missing() -> None:
        emit(
            "-" * 52 + "\n"
            "Required Ollama model is not installed.\n\n"
            f"Configured Model:\n{selected_model}\n\n"
            "Install it:\n"
            f"ollama pull {selected_model}\n\n"
            "Or launch with a different model:\n"
            "GOYATHLAY_OLLAMA_MODEL=qwen2.5-coder:7b ./run_goyathlay.sh\n"
            + "-" * 52
        )

    should_pull = heal_auto
    if not should_pull and (interactive if interactive is not None else sys.stdin.isatty()):
        explain_missing()
        should_pull = input_fn("Pull this model now? [Y/N]: ").strip().casefold() in {"y", "yes"}
    if not should_pull:
        explain_missing()
        return False

    emit(f"Pulling Ollama model {selected_model}...")
    try:
        pull = runner([ollama, "pull", selected_model], capture_output=True, text=True, check=False, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        emit(f"Unable to pull Ollama model {selected_model}: {exc}")
        return False
    if pull.returncode != 0:
        detail = (pull.stderr or pull.stdout or "Ollama model download failed.").strip()
        emit(f"Unable to pull Ollama model {selected_model}:\n{detail}")
        return False

    listing = list_models()
    if listing is None:
        emit("Ollama service became unavailable after the model pull. Start it with: ollama serve")
        return False
    if not _model_is_listed(listing.stdout or "", selected_model):
        emit(f"Model pull completed, but {selected_model} is still missing from `ollama list`.")
        return False
    emit(f"Ollama model verified: {selected_model}")
    return True


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
    input_fn: Callable[[str], str] = input,
    emit: Callable[[str], None] = print,
    interactive: bool | None = None,
    cli_runner: Callable[..., int] = subprocess.call,
) -> int:
    """Preflight Ollama, then start the CLI using this interpreter."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    heal_auto = "--heal-auto" in arguments
    if heal_auto and "--dry-run" in arguments:
        try:
            return cli_runner([sys.executable, "-m", "goyathlay.goyathlay", *arguments])
        except OSError as exc:
            emit(f"Unable to launch Goyathlay: {exc}")
            return 1
    arguments = [argument for argument in arguments if argument != "--heal-auto"]
    if not verify_model(
        runner=runner, which=which, input_fn=input_fn, emit=emit,
        heal_auto=heal_auto, interactive=interactive,
    ):
        return 1
    try:
        return cli_runner([sys.executable, "-m", "goyathlay.goyathlay", *arguments])
    except OSError as exc:
        emit(f"Unable to launch Goyathlay: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
