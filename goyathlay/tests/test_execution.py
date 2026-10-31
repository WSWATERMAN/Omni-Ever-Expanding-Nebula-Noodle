import subprocess
import unittest

from goyathlay.execution import ExecutionError, ExecutionManager


class ExecutionManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = ExecutionManager()

    def test_executes_command_and_captures_stdout(self):
        result = self.manager.execute("echo hello")

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.stdout, "hello\n")
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.returncode, 0)

    def test_rejects_empty_command(self):
        with self.assertRaisesRegex(ExecutionError, "empty"):
            self.manager.execute("")

    def test_rejects_command_that_does_not_exist(self):
        with self.assertRaisesRegex(ExecutionError, "Command not found"):
            self.manager.execute("this_command_does_not_exist")

    def test_rejects_invalid_shell_syntax(self):
        with self.assertRaisesRegex(ExecutionError, "Invalid command syntax"):
            self.manager.execute("echo 'unfinished")


if __name__ == "__main__":
    unittest.main()
