"""Tests for read-only SQLite query execution and output formatting."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from goyathlay.db.sqlite_executor import SqliteExecutionError, SqliteExecutor
from goyathlay.db.sqlite_profiles import SqliteProfile


class SqliteExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "app.db"
        connection = sqlite3.connect(self.database)
        connection.executescript(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            INSERT INTO users(name) VALUES ('Ada'), ('Grace');
            CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id));
            CREATE INDEX idx_users_name ON users(name);
            CREATE VIEW active_users AS SELECT id, name FROM users;
            CREATE TRIGGER users_no_update BEFORE UPDATE ON users BEGIN SELECT RAISE(ABORT, 'readonly'); END;
            """
        )
        connection.commit()
        connection.close()
        self.profile = SqliteProfile("local", str(self.database))
        self.executor = SqliteExecutor()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_execute_select_returns_columns_rows_and_count(self):
        result = self.executor.execute(self.profile, "SELECT id, name FROM users ORDER BY id")

        self.assertEqual(result.columns, ["id", "name"])
        self.assertEqual(result.rows, [(1, "Ada"), (2, "Grace")])
        self.assertEqual(result.row_count, 2)

    def test_result_format_for_scalar_query(self):
        result = self.executor.execute(self.profile, "SELECT COUNT(*) AS total FROM users")

        self.assertEqual(result.columns, ["total"])
        self.assertEqual(result.rows, [(2,)])
        self.assertEqual(result.row_count, 1)

    def test_validation_failure_happens_before_database_open(self):
        missing = SqliteProfile("missing", str(Path(self.temp_dir.name) / "missing.db"))

        with self.assertRaisesRegex(SqliteExecutionError, "SQL validation failed"):
            self.executor.execute(missing, "DELETE FROM users")

        self.assertFalse(Path(missing.database).exists())

    def test_read_only_uri_and_authorizer_reject_writes(self):
        with self.assertRaises(SqliteExecutionError):
            self.executor.execute(self.profile, "UPDATE users SET name = 'Changed'")

        result = self.executor.execute(self.profile, "SELECT name FROM users ORDER BY id")
        self.assertEqual(result.rows[0], ("Ada",))

    def test_rejects_multiple_statements(self):
        with self.assertRaisesRegex(SqliteExecutionError, "Only one SQL statement"):
            self.executor.execute(self.profile, "SELECT 1; SELECT 2")

    def test_rejects_attach_detach_vacuum_and_writable_schema(self):
        statements = (
            "ATTACH DATABASE '/tmp/other.db' AS other",
            "DETACH DATABASE other",
            "VACUUM",
            "PRAGMA writable_schema=ON",
        )
        for statement in statements:
            with self.subTest(statement=statement), self.assertRaises(SqliteExecutionError):
                self.executor.execute(self.profile, statement)

    def test_nonexistent_database_is_not_created(self):
        missing_path = Path(self.temp_dir.name) / "does-not-exist.db"
        missing = SqliteProfile("missing", str(missing_path))

        with self.assertRaises(SqliteExecutionError):
            self.executor.execute(missing, "SELECT 1")

        self.assertFalse(missing_path.exists())


if __name__ == "__main__":
    unittest.main()
