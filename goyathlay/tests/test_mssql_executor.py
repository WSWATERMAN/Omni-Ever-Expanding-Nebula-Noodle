"""Tests for validated SQL Server query execution."""

import unittest
from unittest.mock import Mock, patch

from goyathlay.db.mssql_executor import MssqlExecutionError, MssqlExecutor
from goyathlay.db.mssql_profiles import MssqlProfile, MssqlProfileManager


class MssqlExecutorTests(unittest.TestCase):
    def setUp(self):
        self.profiles = Mock(spec=MssqlProfileManager)
        self.profile = MssqlProfile("prod", "sql01", "inventory", "readonly")
        self.profiles.load_profile.return_value = self.profile
        self.pyodbc = Mock()
        self.connection = Mock()
        self.cursor = Mock()
        self.connection.cursor.return_value = self.cursor
        self.pyodbc.connect.return_value = self.connection
        self.executor = MssqlExecutor(self.profiles, pyodbc_module=self.pyodbc)
        self.sql = "SELECT name FROM sys.databases ORDER BY name;"

    def test_successful_execution_returns_columns_rows_count_and_rolls_back(self):
        self.cursor.description = [("name",)]
        self.cursor.fetchall.return_value = [("app",), ("master",)]

        with patch.dict("os.environ", {"GOYATHLAY_MSSQL_PASSWORD": "p;wd}"}):
            result = self.executor.execute("prod", self.sql)

        self.assertEqual(result.columns, ["name"])
        self.assertEqual(result.rows, [("app",), ("master",)])
        self.assertEqual(result.row_count, 2)
        connection_string = self.pyodbc.connect.call_args.args[0]
        self.assertIn("ApplicationIntent=ReadOnly", connection_string)
        self.assertIn("PWD={p;wd}}}", connection_string)
        self.assertFalse(self.pyodbc.connect.call_args.kwargs["autocommit"])
        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()

    def test_validation_failure_blocks_before_connect(self):
        with patch.dict("os.environ", {"GOYATHLAY_MSSQL_PASSWORD": "secret"}):
            with self.assertRaisesRegex(MssqlExecutionError, "SQL validation failed"):
                self.executor.execute(self.profile, "DROP TABLE users")
        self.pyodbc.connect.assert_not_called()

    def test_missing_password_fails_without_connecting(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(MssqlExecutionError, "GOYATHLAY_MSSQL_PASSWORD"):
                self.executor.execute(self.profile, self.sql)
        self.pyodbc.connect.assert_not_called()

    def test_query_error_rolls_back_and_closes(self):
        self.cursor.execute.side_effect = RuntimeError("server error")
        with patch.dict("os.environ", {"GOYATHLAY_MSSQL_PASSWORD": "secret"}):
            with self.assertRaisesRegex(MssqlExecutionError, "server error"):
                self.executor.execute(self.profile, self.sql)
        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
