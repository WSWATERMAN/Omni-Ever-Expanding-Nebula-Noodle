"""Tests for PostgreSQL intent translation and read-only SQL validation."""

import unittest

from goyathlay.db import (
    DatabaseQuery,
    PostgresInterpreter,
    QueryValidator,
    UnsupportedIntentError,
)


class PostgresInterpreterTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = PostgresInterpreter()

    def test_show_tables(self):
        query = self.interpreter.translate("show tables")
        self.assertEqual(query.engine, "PostgreSQL")
        self.assertEqual(query.intent, "show tables")
        self.assertTrue(query.read_only)
        self.assertEqual(
            query.sql,
            """SELECT
    table_schema,
    table_name
FROM information_schema.tables
ORDER BY table_schema, table_name;""",
        )
        self.assertTrue(self.interpreter.validate(query.sql).allowed)

    def test_show_databases(self):
        query = self.interpreter.translate("show databases")
        self.assertIn("FROM pg_database", query.sql)
        self.assertTrue(query.read_only)

    def test_active_sessions(self):
        query = self.interpreter.translate("show active sessions")
        self.assertIn("FROM pg_stat_activity", query.sql)
        self.assertIn("usename", query.sql)

    def test_largest_tables(self):
        query = self.interpreter.translate("show largest tables")
        self.assertIn("pg_total_relation_size", query.sql)
        self.assertIn("LIMIT 10", query.sql)

    def test_table_sizes(self):
        query = self.interpreter.translate("show table sizes")
        self.assertIn("pg_size_pretty", query.sql)
        self.assertIn("FROM pg_tables", query.sql)

    def test_replication_status(self):
        query = self.interpreter.translate("show replication status")
        self.assertIn("FROM pg_stat_replication", query.sql)
        self.assertTrue(self.interpreter.validate(query.sql).allowed)

    def test_all_documented_intents_translate_and_validate(self):
        intents = (
            "show databases",
            "show tables",
            "show largest tables",
            "show active sessions",
            "show blocking sessions",
            "show long running queries",
            "show database size",
            "show index usage",
            "show table sizes",
            "show replication status",
        )
        for intent in intents:
            with self.subTest(intent=intent):
                query = self.interpreter.translate(intent)
                self.assertIsInstance(query, DatabaseQuery)
                self.assertEqual(query.engine, "PostgreSQL")
                self.assertTrue(query.read_only)
                self.assertTrue(self.interpreter.validate(query.sql).allowed)

    def test_intent_matching_is_case_and_whitespace_insensitive(self):
        query = self.interpreter.translate("  SHOW   TABLES  ")
        self.assertEqual(query.intent, "  SHOW   TABLES  ")
        self.assertIn("information_schema.tables", query.sql)

    def test_unknown_intent_raises(self):
        with self.assertRaises(UnsupportedIntentError):
            self.interpreter.translate("drop the old database")

    def test_empty_intent_raises(self):
        with self.assertRaises(UnsupportedIntentError):
            self.interpreter.translate("  ")


class QueryValidatorTests(unittest.TestCase):
    def setUp(self):
        self.validator = QueryValidator()

    def test_allows_select_with_and_explain(self):
        for sql in ("SELECT 1", "WITH x AS (SELECT 1) SELECT * FROM x", "EXPLAIN SELECT 1"):
            with self.subTest(sql=sql):
                result = self.validator.validate(sql)
                self.assertTrue(result.allowed)
                self.assertIsNone(result.reason)

    def test_blocks_drop_delete_alter_and_other_writes(self):
        for sql in (
            "DROP TABLE users",
            "DELETE FROM users",
            "ALTER TABLE users ADD COLUMN x int",
            "INSERT INTO users VALUES (1)",
            "UPDATE users SET x = 1",
            "TRUNCATE users",
            "CREATE TABLE users (id int)",
            "GRANT SELECT ON users TO app",
            "REVOKE SELECT ON users FROM app",
        ):
            with self.subTest(sql=sql):
                result = self.validator.validate(sql)
                self.assertFalse(result.allowed)
                self.assertIsNotNone(result.reason)

    def test_rejects_write_operation_inside_with_query(self):
        result = self.validator.validate(
            "WITH removed AS (DELETE FROM users RETURNING id) SELECT * FROM removed"
        )
        self.assertFalse(result.allowed)

    def test_ignores_keywords_inside_literals_and_comments(self):
        result = self.validator.validate("SELECT 'DROP TABLE x' -- DELETE FROM x\n;")
        self.assertTrue(result.allowed)

    def test_rejects_multiple_statements(self):
        result = self.validator.validate("SELECT 1; DELETE FROM users;")
        self.assertFalse(result.allowed)
        self.assertIn("one SQL statement", result.reason)

    def test_rejects_empty_and_non_query_sql(self):
        for sql in ("", "  ", "-- just a comment", "UPDATE users SET x = 1"):
            with self.subTest(sql=sql):
                self.assertFalse(self.validator.validate(sql).allowed)


if __name__ == "__main__":
    unittest.main()
