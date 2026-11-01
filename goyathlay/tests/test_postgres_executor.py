"""Tests for validated, read-only PostgreSQL query execution."""

import unittest
from unittest.mock import Mock

from goyathlay.db import DatabaseQuery
from goyathlay.db.executor import PostgresExecutionError, PostgresExecutor


class PostgresExecutorTests(unittest.TestCase):
    def setUp(self):
        self.connection_manager = Mock()
        self.connection = Mock()
        self.cursor = Mock()
        self.connection.cursor.return_value = self.cursor
        self.connection_manager.connect.return_value = self.connection
        self.executor = PostgresExecutor(self.connection_manager)
        self.query = DatabaseQuery("PostgreSQL", "show tables", "SELECT table_name FROM tables;", True)

    def test_successful_execution_returns_rows_columns_and_row_count(self):
        self.cursor.description = [("table_name",), ("schema",)]
        self.cursor.fetchall.return_value = [("users", "public"), ("orders", "public")]

        result = self.executor.execute(self.query)

        self.assertEqual(result.rows, (("users", "public"), ("orders", "public")))
        self.assertEqual(result.columns, ("table_name", "schema"))
        self.assertEqual(result.row_count, 2)
        self.assertEqual(self.cursor.execute.call_args_list[0].args[0], "SET TRANSACTION READ ONLY")
        self.assertEqual(self.cursor.execute.call_args_list[1].args[0], self.query.sql)
        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()
        self.cursor.close.assert_called_once()

    def test_validation_failure_blocks_before_connecting(self):
        unsafe = DatabaseQuery("PostgreSQL", "unsafe", "DROP TABLE users", True)

        with self.assertRaisesRegex(PostgresExecutionError, "SQL validation failed"):
            self.executor.execute(unsafe)

        self.connection_manager.connect.assert_not_called()

    def test_query_marked_not_read_only_is_blocked(self):
        unsafe = DatabaseQuery("PostgreSQL", "unsafe", "SELECT 1", False)

        with self.assertRaisesRegex(PostgresExecutionError, "marked read-only"):
            self.executor.execute(unsafe)

        self.connection_manager.connect.assert_not_called()

    def test_empty_result_has_columns_and_zero_rows(self):
        self.cursor.description = [("pid",)]
        self.cursor.fetchall.return_value = []

        result = self.executor.execute(self.query)

        self.assertEqual(result.rows, ())
        self.assertEqual(result.columns, ("pid",))
        self.assertEqual(result.row_count, 0)

    def test_query_error_rolls_back_and_closes(self):
        self.cursor.execute.side_effect = [None, RuntimeError("query failed")]

        with self.assertRaisesRegex(PostgresExecutionError, "query failed"):
            self.executor.execute(self.query)

        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()
        self.cursor.close.assert_called_once()

    def test_rollback_occurs_when_read_only_transaction_setup_fails(self):
        self.cursor.execute.side_effect = RuntimeError("read-only unavailable")

        with self.assertRaises(PostgresExecutionError):
            self.executor.execute(self.query)

        self.cursor.execute.assert_called_once_with("SET TRANSACTION READ ONLY")
        self.connection.rollback.assert_called_once()
        self.connection.close.assert_called_once()

    def test_rollback_failure_is_reported_after_connection_cleanup(self):
        self.cursor.description = [("value",)]
        self.cursor.fetchall.return_value = [(1,)]
        self.connection.rollback.side_effect = RuntimeError("rollback failed")

        with self.assertRaisesRegex(PostgresExecutionError, "rollback failed"):
            self.executor.execute(self.query)

        self.connection.close.assert_called_once()
        self.cursor.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
