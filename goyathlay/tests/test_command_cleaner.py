import unittest

from goyathlay.command_cleaner import clean_command


class CleanCommandTests(unittest.TestCase):
    def test_removes_bash_fence(self):
        self.assertEqual(clean_command("```bash\nnetstat -tuln\n```"), "netstat -tuln")

    def test_removes_fence_without_language(self):
        self.assertEqual(clean_command("```\nls -la\n```"), "ls -la")

    def test_strips_surrounding_whitespace_without_fence(self):
        self.assertEqual(clean_command("  pwd\n"), "pwd")

    def test_preserves_backticks_inside_command(self):
        command = "printf '%s\\n' `date`"
        self.assertEqual(clean_command(command), command)


if __name__ == "__main__":
    unittest.main()
