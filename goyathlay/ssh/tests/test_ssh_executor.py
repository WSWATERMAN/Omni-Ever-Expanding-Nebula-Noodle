"""Tests for SSH command output and exit status capture."""

import unittest
from unittest.mock import Mock

from goyathlay.ssh.executor import SSHExecutionError, SSHExecutionResult, SSHExecutor


class FakeChannel:
    def __init__(self, stdout=b"remote output\n", stderr=b"", exit_code=0):
        self.stdout = [stdout] if stdout else []
        self.stderr = [stderr] if stderr else []
        self.exit_code = exit_code

    def exit_status_ready(self):
        return True

    def recv_ready(self):
        return bool(self.stdout)

    def recv_stderr_ready(self):
        return bool(self.stderr)

    def recv(self, size):
        return self.stdout.pop(0)

    def recv_stderr(self, size):
        return self.stderr.pop(0)

    def recv_exit_status(self):
        return self.exit_code


class SSHExecutorTests(unittest.TestCase):
    def run_command(self, exit_code=0, stdout=b"remote output\n", stderr=b"remote warning\n"):
        channel = FakeChannel(stdout, stderr, exit_code)
        stdout_file = Mock(channel=channel)
        stderr_file = Mock(channel=channel)
        client = Mock()
        client.exec_command.return_value = (Mock(), stdout_file, stderr_file)
        return SSHExecutor().execute(client, "printf approved"), client

    def test_captures_stdout_stderr_and_exit_code(self):
        result, client = self.run_command()

        self.assertEqual(
            result,
            SSHExecutionResult("remote output\n", "remote warning\n", 0),
        )
        client.exec_command.assert_called_once_with("printf approved", get_pty=False)

    def test_nonzero_exit_code_is_returned(self):
        result, _ = self.run_command(exit_code=17, stdout=b"", stderr=b"failed")

        self.assertEqual(result.exit_code, 17)
        self.assertEqual(result.stderr, "failed")

    def test_remote_exec_error_is_wrapped(self):
        client = Mock()
        client.exec_command.side_effect = OSError("connection closed")

        with self.assertRaisesRegex(SSHExecutionError, "connection closed"):
            SSHExecutor().execute(client, "true")

    def test_empty_command_is_rejected(self):
        with self.assertRaises(ValueError):
            SSHExecutor().execute(Mock(), "  ")


if __name__ == "__main__":
    unittest.main()
