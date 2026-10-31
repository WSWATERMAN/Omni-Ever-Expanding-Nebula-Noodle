import unittest
from unittest.mock import patch

from goyathlay.approval import ApprovalManager


class ApprovalManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = ApprovalManager()

    @patch("builtins.input", side_effect=["A"])
    def test_approve_returns_original_command(self, mock_input):
        self.assertEqual(self.manager.review("netstat -tuln"), (True, "netstat -tuln"))
        mock_input.assert_called_once()

    @patch("builtins.input", side_effect=["E", "ss -tulpn"])
    def test_edit_returns_user_command(self, mock_input):
        self.assertEqual(self.manager.review("netstat -tuln"), (True, "ss -tulpn"))
        self.assertEqual(mock_input.call_count, 2)

    @patch("builtins.input", side_effect=["C"])
    def test_cancel_returns_no_command(self, mock_input):
        self.assertEqual(self.manager.review("netstat -tuln"), (False, None))
        mock_input.assert_called_once()

    @patch("builtins.input", side_effect=["banana", "A"])
    def test_invalid_selection_prompts_again(self, mock_input):
        self.assertEqual(self.manager.review("netstat -tuln"), (True, "netstat -tuln"))
        self.assertEqual(mock_input.call_count, 2)

    @patch("builtins.input", side_effect=["approve"])
    def test_accepts_full_word_case_insensitively(self, mock_input):
        self.assertEqual(self.manager.review("ls -la"), (True, "ls -la"))


if __name__ == "__main__":
    unittest.main()
