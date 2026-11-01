#!/usr/bin/env python3
"""Install and repair Goyathlay with staged virtual-environment replacement."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Sequence


MINIMUM_PYTHON = (3, 12)
REQUIRED_MODEL = "qwen2.5-coder:7b"
REQUIRED_IMPORTS = {"ollama": "ollama", "paramiko": "paramiko"}


class InstallationError(RuntimeError):
    """Raised when installation cannot be safely completed."""


def parse_python_version(output: str) -> tuple[int, int, int] | None:
    """Extract a Python version tuple from `python3 --version` output."""
    match = re.search(r"Python\s+(\d+)\.(\d+)(?:\.(\d+))?", output)
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def failed_package(output: str, fallback: str = "requirements.txt") -> str:
    """Extract the package named by common pip failure messages."""
    patterns = (
        r"Could not find a version that satisfies the requirement\s+([^\s(]+)",
        r"No matching distribution found for\s+([^\s]+)",
        r"Failed building wheel for\s+([^\s]+)",
        r"Could not build wheels for\s+([^\s,]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, output, flags=re.IGNORECASE)
        if match:
            return match.group(1).rstrip(".,")
    return fallback


class Installer:
    """Run checks and repairs, retaining the old environment until validation."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
        sleeper: Callable[[float], None] = time.sleep,
        emit: Callable[[str], None] = print,
    ) -> None:
        self.root = Path(root).resolve() if root else Path(__file__).resolve().parents[1]
        self.venv = self.root / ".venv-goyathlay"
        self.staging = self.root / ".venv-goyathlay.installing"
        self.requirements = self.root / "requirements.txt"
        self.runner = runner
        self.popen = popen
        self.sleeper = sleeper
        self.emit = emit
        self.ollama_executable: str | None = None
        self._owns_staging = False

    def _report(self, step: str, cause: str, attempted: str, result: str) -> None:
        self.emit(f"\n[{step}]\nCause: {cause}\nAttempted Fix: {attempted}\nResult: {result}")

    def _run(
        self,
        command: Sequence[str | Path],
        *,
        check: bool = True,
        timeout: int | None = 60,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        args = [str(part) for part in command]
        try:
            result = self.runner(
                args,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            if check:
                raise InstallationError(f"Command failed to run: {' '.join(args)}: {exc}") from exc
            return subprocess.CompletedProcess(args, 127, "", str(exc))
        if check and result.returncode != 0:
            details = (result.stderr or result.stdout or "No command output.").strip()
            raise InstallationError(f"Command failed ({result.returncode}): {' '.join(args)}\n{details}")
        return result

    def check_python(self) -> str:
        """Locate Python 3.12+ and return its executable path."""
        path_python = shutil.which("python3")
        candidates: list[str] = []
        # If invoked from an activated venv, use its base interpreter to avoid
        # building a replacement venv from the environment being repaired.
        base_python = getattr(sys, "_base_executable", None)
        if sys.prefix != sys.base_prefix and base_python:
            candidates.append(base_python)
        if path_python and path_python not in candidates:
            candidates.append(path_python)
        if not candidates:
            raise InstallationError("ERROR:\nPython 3.12 or newer is required. `python3` was not found.")
        versions: list[str] = []
        for python in candidates:
            result = self._run([python, "--version"], check=False)
            version = parse_python_version(result.stdout + result.stderr)
            found = (result.stdout + result.stderr).strip() or "unknown version"
            versions.append(found)
            if result.returncode == 0 and version is not None and version >= MINIMUM_PYTHON:
                self._report("Python", f"Found {found}.", "No repair needed.", "Python version is supported.")
                return python
        raise InstallationError(
            "ERROR:\nPython 3.12 or newer is required.\n"
            f"Found: {', '.join(versions)}\nInstall a supported Python 3 release and retry."
        )

    def _venv_is_healthy(self, path: Path) -> tuple[bool, str]:
        python = path / "bin" / "python"
        pip = path / "bin" / "pip"
        if path.is_symlink() or not path.is_dir():
            return False, "virtual environment directory is missing or is a symlink"
        if python.is_symlink() and not python.exists():
            return False, "virtual environment Python symlink is broken"
        if not python.is_file() or not os.access(python, os.X_OK):
            return False, "virtual environment Python executable is missing"
        if pip.is_symlink() and not pip.exists():
            return False, "virtual environment pip symlink is broken"
        if not pip.is_file() or not os.access(pip, os.X_OK):
            return False, "virtual environment pip executable is missing"
        python_version = self._run([python, "--version"], check=False)
        version = parse_python_version(python_version.stdout + python_version.stderr)
        if python_version.returncode != 0 or version is None or version < MINIMUM_PYTHON:
            return False, "virtual environment Python is unsupported or cannot start"
        prefix_check = self._run(
            [python, "-c", "import sys; raise SystemExit(sys.prefix == sys.base_prefix)"], check=False
        )
        if prefix_check.returncode != 0:
            return False, "Python executable is not operating as an isolated virtual environment"
        pip_check = self._run([python, "-m", "pip", "--version"], check=False)
        if pip_check.returncode != 0:
            return False, "`python -m pip --version` failed"
        import_check = self._run(
            [python, "-c", "import ollama, paramiko"], check=False
        )
        if import_check.returncode != 0:
            return False, _missing_import(import_check.stderr or import_check.stdout)
        return True, "Python, pip, Ollama, and Paramiko are available"

    def prepare_environment(self, python3: str) -> tuple[Path, bool]:
        """Reuse a healthy venv or construct a validated staged replacement."""
        healthy, cause = self._venv_is_healthy(self.venv)
        if healthy:
            self._report("Virtual environment", cause, "Reuse existing environment.", "Ready.")
            self._report("Dependencies", "Required imports are present.",
                         "No package installation needed.", "OK.")
            return self.venv / "bin" / "python", False

        if self.venv.is_symlink():
            raise InstallationError(f"Refusing to replace symlink virtual environment: {self.venv}")

        self._report("Virtual environment", cause,
                     "Build a replacement in a staging directory; keep the existing environment intact.",
                     "Repair required.")
        self._build_staging_environment(python3)
        return self.staging / "bin" / "python", True

    def _build_staging_environment(self, python3: str) -> None:
        """Build and populate a fresh environment without disturbing the active one."""
        if self.staging.is_symlink():
            raise InstallationError(f"Refusing to remove symlink staging path: {self.staging}")
        if self.staging.exists():
            raise InstallationError(
                f"Installer staging path already exists; it was preserved for inspection: {self.staging}"
            )
        self._owns_staging = True
        self._run([python3, "-m", "venv", self.staging])
        staged_python = self.staging / "bin" / "python"
        pip_check = self._run([staged_python, "-m", "pip", "--version"], check=False)
        if pip_check.returncode != 0:
            self._report("pip", "pip is missing or broken in the new environment.",
                         "Run `python -m ensurepip --upgrade`, then retry pip validation.", "Repairing.")
            self._run([staged_python, "-m", "ensurepip", "--upgrade"], check=False)
            pip_check = self._run([staged_python, "-m", "pip", "--version"], check=False)
            if pip_check.returncode != 0:
                self._report("pip", "ensurepip did not restore pip.",
                             "Rebuild the staged environment once and retry.", "Rebuilding.")
                shutil.rmtree(self.staging, ignore_errors=True)
                self._run([python3, "-m", "venv", self.staging])
                staged_python = self.staging / "bin" / "python"
                pip_check = self._run([staged_python, "-m", "pip", "--version"], check=False)
                if pip_check.returncode != 0:
                    raise InstallationError("pip remains unavailable after rebuilding the virtual environment.")

        if not self.requirements.is_file():
            raise InstallationError(f"Required dependency file is missing: {self.requirements}")
        upgrade = self._run(
            [staged_python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
            check=False,
        )
        if upgrade.returncode != 0:
            details = (upgrade.stderr or upgrade.stdout or "No pip output.").strip()
            package = failed_package(details, "pip/setuptools/wheel")
            self._report("Build tools", f"Installation of {package} failed.",
                         "Upgrade pip, setuptools, and wheel in the staging environment.",
                         f"Failed; details:\n{details}")
            raise InstallationError(f"Failed to install or upgrade package {package}.\n{details}")
        install = self._run(
            [staged_python, "-m", "pip", "install", "-r", self.requirements], check=False, timeout=600
        )
        if install.returncode != 0:
            details = (install.stderr or install.stdout or "No pip output.").strip()
            package = failed_package(details)
            self._report("Dependencies", f"Installation of {package} failed.",
                         "pip install -r requirements.txt", f"Failed; details:\n{details}")
            raise InstallationError(f"Failed to install package {package}.\n{details}")
        import_check = self._run([staged_python, "-c", "import ollama, paramiko"], check=False)
        if import_check.returncode != 0:
            missing = _missing_import(import_check.stderr or import_check.stdout)
            distribution = REQUIRED_IMPORTS.get(missing, missing)
            self._report("Dependencies", f"Python import {missing!r} failed.",
                         f"Install package {distribution} directly and retry the import.", "Repairing.")
            repair = self._run(
                [staged_python, "-m", "pip", "install", distribution], check=False, timeout=600
            )
            retry = self._run([staged_python, "-c", "import ollama, paramiko"], check=False)
            if repair.returncode != 0 or retry.returncode != 0:
                details = (repair.stderr or repair.stdout or retry.stderr or retry.stdout).strip()
                raise InstallationError(f"Required package {distribution} is still unavailable.\n{details}")
        self._report("Dependencies", "New environment required packages were installed.",
                     "pip upgraded and requirements installed.", "OK.")

    def verify_ollama_cli(self) -> str:
        """Require the Ollama executable and verify its version command."""
        executable = shutil.which("ollama")
        if not executable:
            raise InstallationError(
                "Ollama is not installed.\nInstall it from https://ollama.com, then rerun the installer."
            )
        result = self._run([executable, "--version"], check=False)
        if result.returncode != 0:
            raise InstallationError(f"Ollama executable was found but `ollama --version` failed: {result.stderr}")
        self.ollama_executable = executable
        self._report("Ollama", "Ollama executable found.", "Checked `ollama --version`.", "OK.")
        return executable

    def _ollama_list(self, executable: str) -> subprocess.CompletedProcess[str]:
        return self._run([executable, "list"], check=False, timeout=20)

    def verify_ollama_service(self, executable: str) -> str:
        """Check local daemon and launch `ollama serve` if it is not responding."""
        result = self._ollama_list(executable)
        if result.returncode == 0:
            self._report("Ollama service", "Local daemon responded to `ollama list`.",
                         "No repair needed.", "Running.")
            return result.stdout

        cause = (result.stderr or result.stdout or "ollama list failed").strip()
        self._report("Ollama service", cause, "Start local `ollama serve` and retry for up to 10 seconds.",
                     "Attempting repair.")
        try:
            self.popen(
                [executable, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, start_new_session=True,
            )
        except OSError as exc:
            raise InstallationError(f"Unable to start Ollama service: {exc}") from exc
        for _attempt in range(10):
            self.sleeper(1)
            result = self._ollama_list(executable)
            if result.returncode == 0:
                self._report("Ollama service", cause, "Started `ollama serve`.", "Service is running.")
                return result.stdout
        raise InstallationError("Unable to start Ollama service. Start Ollama manually and rerun the installer.")

    def verify_model(self, executable: str, listing: str) -> None:
        """Pull the required local model only when absent, then verify it."""
        if _has_model(listing, REQUIRED_MODEL):
            self._report("Model", f"{REQUIRED_MODEL} is installed.", "No model download needed.", "OK.")
            return
        self._report("Model", f"{REQUIRED_MODEL} is missing.",
                     f"Run `ollama pull {REQUIRED_MODEL}`.", "Downloading model.")
        pull = self._run([executable, "pull", REQUIRED_MODEL], check=False, timeout=3600)
        if pull.returncode != 0:
            details = (pull.stderr or pull.stdout or "No Ollama output.").strip()
            raise InstallationError(f"Failed to pull model {REQUIRED_MODEL}.\n{details}")
        listing = self._ollama_list(executable)
        if listing.returncode != 0 or not _has_model(listing.stdout, REQUIRED_MODEL):
            raise InstallationError(f"Model {REQUIRED_MODEL} is still unavailable after `ollama pull`.")
        self._report("Model", f"{REQUIRED_MODEL} was missing.", "Pulled model and rechecked `ollama list`.", "OK.")

    def ensure_runtime_directory(self) -> Path:
        """Create and permission-check the user's Goyathlay data directory."""
        directory = Path.home() / ".goyathlay"
        if directory.is_symlink():
            raise InstallationError(f"Refusing to use symlink configuration directory: {directory}")
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory.chmod(0o700)
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".installer-check-", delete=True):
                pass
        except OSError as exc:
            raise InstallationError(f"Configuration directory is not writable: {directory}: {exc}") from exc
        self._report("Runtime directory", str(directory), "Create it if missing and set mode 0700.", "Writable and private.")
        return directory

    def post_install_validation(self, python: Path) -> None:
        """Validate imports, CLI startup/version, and local model response."""
        self._run([python, "-c", "import ollama, paramiko; from goyathlay.providers.ollama_provider import OllamaProvider; print('provider-ok')"])
        version = self._run([python, "-m", "goyathlay.goyathlay", "--version"])
        self.emit(version.stdout.strip())
        env = os.environ.copy()
        env["GOYATHLAY_OLLAMA_MODEL"] = REQUIRED_MODEL
        smoke = self._run(
            [python, "-c", "from goyathlay.providers.ollama_provider import OllamaProvider; "
             "command=OllamaProvider().generate_command('show listening ports'); "
             "assert isinstance(command, str) and command.strip(); print('smoke-ok')"],
            timeout=240,
            env=env,
        )
        if "smoke-ok" not in smoke.stdout:
            raise InstallationError("Local Ollama smoke test returned no command response.")

    def _activate_staging(self) -> None:
        """Atomically replace a broken venv and restore it if rename fails."""
        backup = self.root / ".venv-goyathlay.previous"
        if backup.is_symlink():
            raise InstallationError(f"Refusing to use symlink backup path: {backup}")
        if backup.exists():
            raise InstallationError(f"Previous environment backup already exists; preserved at {backup}")
        moved_old = False
        try:
            if self.venv.is_symlink():
                raise InstallationError(f"Refusing to replace symlink virtual environment: {self.venv}")
            if self.venv.exists():
                os.replace(self.venv, backup)
                moved_old = True
            os.replace(self.staging, self.venv)
            self._owns_staging = False
        except OSError as exc:
            if moved_old and not self.venv.exists() and backup.exists():
                os.replace(backup, self.venv)
            raise InstallationError(f"Could not activate repaired environment: {exc}") from exc
        if backup.exists():
            try:
                shutil.rmtree(backup)
            except OSError as exc:
                self.emit(f"Warning: repaired environment is active, but old venv cleanup failed: {exc}")

    def install(self) -> None:
        """Run all checks; commit a staged venv only after end-to-end validation."""
        is_staged = False
        try:
            python3 = self.check_python()
            python, is_staged = self.prepare_environment(python3)
            ollama = self.verify_ollama_cli()
            listing = self.verify_ollama_service(ollama)
            self.verify_model(ollama, listing)
            self.ensure_runtime_directory()
            self.post_install_validation(python)
            if is_staged:
                self._activate_staging()
            self.emit("\n====================================")
            self.emit("GOYATHLAY INSTALLATION COMPLETE")
            self.emit("====================================")
            self.emit("Python: OK\nVirtual Environment: OK\nDependencies: OK\nOllama: OK\nModel: OK\nRuntime: OK")
            self.emit("\nLaunch:\nsource .venv-goyathlay/bin/activate\npython3 -m goyathlay.goyathlay")
        except Exception:
            if self._owns_staging and self.staging.exists():
                shutil.rmtree(self.staging, ignore_errors=True)
            raise


def _missing_import(output: str) -> str:
    match = re.search(r"No module named ['\"]([^'\"]+)", output)
    return match.group(1).split(".")[0] if match else "required runtime dependency"


def _has_model(listing: str, required: str) -> bool:
    return any(line.split() and line.split()[0] == required for line in listing.splitlines()[1:])


def main() -> int:
    """Run installer and return a process exit status suitable for scripts."""
    try:
        Installer().install()
    except InstallationError as exc:
        print(f"\nINSTALLATION FAILED\nCause: {exc}\nAttempted Fix: See the step diagnostics above.\nResult: Not installed.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInstallation interrupted. Existing environment was left in place.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\nINSTALLATION FAILED\nCause: {exc}\nAttempted Fix: See the step diagnostics above.\nResult: Not installed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
