"""Unit tests for installer checks and failure recovery boundaries."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.install_goyathlay import (
    InstallationError,
    Installer,
    _has_model,
    failed_package,
    parse_python_version,
)


class InstallerHelperTests(unittest.TestCase):
    def test_python_version_detection_requires_312(self):
        self.assertEqual(parse_python_version("Python 3.12.1"), (3, 12, 1))
        self.assertEqual(parse_python_version("Python 3.14"), (3, 14, 0))
        self.assertIsNone(parse_python_version("not python"))

    def test_uses_base_python_when_launched_inside_venv(self):
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp, runner=Mock(return_value=subprocess.CompletedProcess(
                [], 0, "Python 3.12.1", ""
            )), emit=Mock())
            with (
                patch("scripts.install_goyathlay.shutil.which", return_value="/env/bin/python3"),
                patch("scripts.install_goyathlay.sys.prefix", "/env"),
                patch("scripts.install_goyathlay.sys.base_prefix", "/system"),
                patch("scripts.install_goyathlay.sys._base_executable", "/system/bin/python3"),
            ):
                self.assertEqual(installer.check_python(), "/system/bin/python3")

    def test_pip_failure_names_package(self):
        self.assertEqual(
            failed_package("ERROR: No matching distribution found for ollama==99"),
            "ollama==99",
        )

    def test_model_detection_matches_name_column(self):
        listing = "NAME ID SIZE MODIFIED\nqwen2.5-coder:7b abc 4GB 2 days ago\n"
        self.assertTrue(_has_model(listing, "qwen2.5-coder:7b"))
        self.assertFalse(_has_model(listing, "qwen2.5:1.5b"))

    def test_installer_uses_configured_model_or_application_default(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(Installer(temp).model, "qwen2.5-coder:14b")
            with patch.dict("os.environ", {"GOYATHLAY_OLLAMA_MODEL": "qwen2.5-coder:7b"}):
                self.assertEqual(Installer(temp).model, "qwen2.5-coder:7b")

    def test_broken_venv_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp, runner=Mock())
            healthy, cause = installer._venv_is_healthy(installer.venv)
        self.assertFalse(healthy)
        self.assertIn("missing", cause)

    def test_missing_pip_executable_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp, runner=Mock())
            (installer.venv / "bin").mkdir(parents=True)
            python = installer.venv / "bin" / "python"
            python.touch()
            python.chmod(0o755)
            healthy, cause = installer._venv_is_healthy(installer.venv)
        self.assertFalse(healthy)
        self.assertIn("pip executable is missing", cause)

    def test_missing_ollama_package_marks_venv_for_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp)
            (installer.venv / "bin").mkdir(parents=True)
            for filename in ("python", "pip"):
                path = installer.venv / "bin" / filename
                path.touch()
                path.chmod(0o755)
            installer.runner = Mock(side_effect=[
                subprocess.CompletedProcess([], 0, "Python 3.12.1", ""),
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "pip 24", ""),
                subprocess.CompletedProcess([], 1, "", "ModuleNotFoundError: No module named 'ollama'"),
            ])
            healthy, cause = installer._venv_is_healthy(installer.venv)
        self.assertFalse(healthy)
        self.assertEqual(cause, "ollama")

    def test_missing_pip_module_marks_venv_for_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp)
            (installer.venv / "bin").mkdir(parents=True)
            for filename in ("python", "pip"):
                path = installer.venv / "bin" / filename
                path.touch()
                path.chmod(0o755)
            installer.runner = Mock(side_effect=[
                subprocess.CompletedProcess([], 0, "Python 3.12.1", ""),
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 1, "", "No module named pip"),
            ])
            healthy, cause = installer._venv_is_healthy(installer.venv)
        self.assertFalse(healthy)
        self.assertEqual(cause, "`python -m pip --version` failed")

    def test_missing_model_is_pulled_then_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp, runner=Mock(side_effect=[
                subprocess.CompletedProcess([], 0, "download complete", ""),
                subprocess.CompletedProcess([], 0, "NAME ID SIZE\nqwen2.5-coder:14b abc 9GB\n", ""),
            ]), emit=Mock())
            installer.verify_model("/usr/bin/ollama", "NAME ID SIZE\nqwen2.5:1.5b abc 1GB\n")
        self.assertEqual(installer.runner.call_count, 2)

    def test_successful_install_orchestration(self):
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp, emit=Mock())
            with (
                patch.object(installer, "check_python", return_value="/usr/bin/python3"),
                patch.object(installer, "prepare_environment", return_value=(Path(temp) / "venv/bin/python", False)),
                patch.object(installer, "verify_ollama_cli", return_value="/usr/local/bin/ollama"),
                patch.object(installer, "verify_ollama_service", return_value="NAME ID SIZE MODIFIED\nqwen2.5-coder:7b abc\n"),
                patch.object(installer, "verify_model") as verify_model,
                patch.object(installer, "ensure_runtime_directory"),
                patch.object(installer, "post_install_validation"),
            ):
                installer.install()
            verify_model.assert_called_once()

    def test_staging_attempts_ensurepip_when_pip_is_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp)
            installer.requirements.write_text("ollama\nparamiko\n")
            calls = []
            pip_checks = 0

            def run(args, **kwargs):
                nonlocal pip_checks
                calls.append(args)
                if args[-2:] == ["-m", "venv"]:
                    self.fail("unexpected venv invocation shape")
                if args[1:4] == ["-m", "venv", str(installer.staging)]:
                    return subprocess.CompletedProcess(args, 0, "", "")
                if args[1:4] == ["-m", "pip", "--version"]:
                    pip_checks += 1
                    return subprocess.CompletedProcess(args, 1 if pip_checks == 1 else 0, "", "")
                return subprocess.CompletedProcess(args, 0, "", "")

            installer.runner = run
            installer._build_staging_environment("python3")

        self.assertTrue(any("ensurepip" in args for args in calls))
        self.assertTrue(any(args[-2:] == ["-r", str(installer.requirements)] for args in calls))

    def test_missing_package_import_is_repaired_and_retested(self):
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp)
            installer.requirements.write_text("ollama\nparamiko\n")
            calls = []
            import_checks = 0

            def run(args, **kwargs):
                nonlocal import_checks
                calls.append(args)
                if args[1:4] == ["-m", "venv", str(installer.staging)]:
                    return subprocess.CompletedProcess(args, 0, "", "")
                if args[1:4] == ["-m", "pip", "--version"]:
                    return subprocess.CompletedProcess(args, 0, "pip 24", "")
                if args[1:3] == ["-c", "import ollama, paramiko"]:
                    import_checks += 1
                    if import_checks == 1:
                        return subprocess.CompletedProcess(args, 1, "", "No module named 'ollama'")
                return subprocess.CompletedProcess(args, 0, "", "")

            installer.runner = run
            installer._build_staging_environment("python3")

        self.assertTrue(any(args[-2:] == ["install", "ollama"] for args in calls))
        self.assertEqual(import_checks, 2)

    def test_service_failure_starts_daemon_and_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp, sleeper=Mock(), popen=Mock())
            installer.runner = Mock(side_effect=[
                subprocess.CompletedProcess([], 1, "", "connection refused"),
                subprocess.CompletedProcess([], 0, "NAME ID SIZE\n", ""),
            ])
            output = installer.verify_ollama_service("/usr/bin/ollama")
        installer.popen.assert_called_once()
        installer.sleeper.assert_called_once_with(1)
        self.assertIn("NAME ID", output)

    def test_failed_validation_preserves_existing_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            installer = Installer(temp, emit=Mock())
            marker = installer.venv / "keep-me"
            installer.venv.mkdir()
            marker.write_text("existing environment")
            installer.staging.mkdir()
            installer._owns_staging = True
            with (
                patch.object(installer, "check_python", return_value="/usr/bin/python3"),
                patch.object(installer, "prepare_environment", return_value=(installer.staging / "bin/python", True)),
                patch.object(installer, "verify_ollama_cli", side_effect=InstallationError("missing Ollama")),
            ):
                with self.assertRaisesRegex(InstallationError, "missing Ollama"):
                    installer.install()
            self.assertEqual(marker.read_text(), "existing environment")
            self.assertFalse(installer.staging.exists())


if __name__ == "__main__":
    unittest.main()
