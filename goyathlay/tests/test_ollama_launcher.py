"""Tests for Ollama preflight before launching the operator console."""

import os
import subprocess
import unittest
from unittest.mock import Mock, patch

from goyathlay.launcher import DEFAULT_MODEL, main, verify_model


def completed(args, code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, code, stdout, stderr)


class OllamaLauncherTests(unittest.TestCase):
    def test_model_present(self):
        runner = Mock(return_value=completed([], stdout="NAME ID SIZE MODIFIED\nqwen2.5-coder:14b abc 9GB now\n"))
        self.assertTrue(verify_model(runner=runner, which=lambda name: "/usr/bin/ollama", interactive=False, emit=Mock()))
        runner.assert_called_once()
        self.assertEqual(runner.call_args.args[0], ["/usr/bin/ollama", "list"])

    def test_missing_model_prints_pull_instructions_and_fails(self):
        runner = Mock(return_value=completed([], stdout="NAME ID SIZE MODIFIED\nqwen2.5:1.5b abc 1GB now\n"))
        emit = Mock()
        self.assertFalse(verify_model(runner=runner, which=lambda name: "/usr/bin/ollama", interactive=False, emit=emit))
        self.assertIn("ollama pull qwen2.5-coder:14b", emit.call_args.args[0])

    def test_alternate_model_from_environment(self):
        runner = Mock(return_value=completed([], stdout="NAME ID SIZE MODIFIED\nqwen2.5-coder:7b abc 4GB now\n"))
        with patch.dict(os.environ, {"GOYATHLAY_OLLAMA_MODEL": "qwen2.5-coder:7b"}):
            self.assertTrue(verify_model(runner=runner, which=lambda name: "/usr/bin/ollama", interactive=False, emit=Mock()))
        self.assertEqual(DEFAULT_MODEL, "qwen2.5-coder:14b")

    def test_daemon_unavailable_blocks_launch(self):
        runner = Mock(return_value=completed([], code=1, stderr="connection refused"))
        emit = Mock()
        self.assertFalse(verify_model(runner=runner, which=lambda name: "/usr/bin/ollama", emit=emit))
        self.assertIn("ollama serve", emit.call_args.args[0])

    def test_ollama_executable_missing_blocks_launch(self):
        emit = Mock()
        self.assertFalse(verify_model(which=lambda name: None, emit=emit, interactive=False))
        self.assertIn("Ollama is not installed", emit.call_args.args[0])

    def test_heal_auto_pulls_missing_model_and_revalidates(self):
        runner = Mock(side_effect=[
            completed([], stdout="NAME ID SIZE\n"),
            completed([]),
            completed([], stdout="NAME ID SIZE\nqwen2.5-coder:14b abc 9GB\n"),
        ])
        self.assertTrue(verify_model(runner=runner, which=lambda name: "/usr/bin/ollama", heal_auto=True, emit=Mock()))
        self.assertEqual([call.args[0][1:] for call in runner.call_args_list], [
            ["list"], ["pull", "qwen2.5-coder:14b"], ["list"],
        ])

    def test_launch_is_blocked_when_preflight_fails(self):
        runner = Mock(return_value=completed([], code=1, stderr="connection refused"))
        cli_runner = Mock()
        result = main([], runner=runner, which=lambda name: "/usr/bin/ollama", emit=Mock(),
                      interactive=False, cli_runner=cli_runner)
        self.assertEqual(result, 1)
        cli_runner.assert_not_called()

    def test_launch_passes_arguments_and_consumes_heal_auto_flag(self):
        runner = Mock(return_value=completed([], stdout="NAME ID SIZE\nqwen2.5-coder:14b abc 9GB\n"))
        cli_runner = Mock(return_value=0)
        result = main(["--heal-auto", "--version"], runner=runner,
                      which=lambda name: "/usr/bin/ollama", emit=Mock(),
                      interactive=False, cli_runner=cli_runner)
        self.assertEqual(result, 0)
        self.assertEqual(cli_runner.call_args.args[0][-3:], ["-m", "goyathlay.goyathlay", "--version"])

    def test_dry_run_flag_prevents_auto_model_pull(self):
        runner = Mock()
        cli_runner = Mock(return_value=0)
        result = main(["--heal-auto", "--dry-run"], runner=runner,
                      which=lambda name: None, emit=Mock(), cli_runner=cli_runner)
        self.assertEqual(result, 0)
        runner.assert_not_called()
        self.assertEqual(cli_runner.call_args.args[0][-2:], ["--heal-auto", "--dry-run"])


if __name__ == "__main__":
    unittest.main()
