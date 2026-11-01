"""Tests for PostgreSQL intent translation and read-only SQL validation."""

import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from goyathlay.db import (
    DatabaseQuery,
    PostgresInterpreter,
    QueryValidator,
    UnsupportedIntentError,
)
from goyathlay.db.executor import PostgresExecutionResult
from goyathlay.db.profiles import DbProfile
from goyathlay import goyathlay
from goyathlay.audit import AuditRecord
from goyathlay.risk import RiskEngine
from goyathlay.profiles import PolicyProfile


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


class PostgresCliIntegrationTests(unittest.TestCase):
    def test_main_routes_database_prompt_without_calling_ollama(self):
        profile = DbProfile("prod", "db01", 5432, "postgres", "readonly")
        database_manager = Mock()
        database_manager.load_profile.return_value = profile
        database_manager.profile_store.default_name = "prod"
        sql = PostgresInterpreter().translate("show tables").sql
        approval = Mock()
        approval.review.return_value = (True, sql)
        executor = Mock()
        executor.execute.return_value = PostgresExecutionResult((("users",),), ("table_name",), 1)
        audit = Mock()
        maintenance = Mock()
        maintenance.is_allowed.return_value = True
        policies = Mock()
        policies.get_default_profile.return_value = PolicyProfile("development", True, True, 0)
        knowledge = Mock()
        knowledge.get_approved.return_value = None
        output = io.StringIO()

        with (
            patch.object(goyathlay, "_create_provider") as provider_factory,
            patch.object(goyathlay, "ApprovalManager", return_value=approval),
            patch.object(goyathlay, "ExecutionManager"),
            patch.object(goyathlay, "FeedbackManager") as feedback_class,
            patch.object(goyathlay, "CommandCache"),
            patch.object(goyathlay, "KnowledgeBase", return_value=knowledge),
            patch.object(goyathlay, "migrate_legacy_data", return_value={"imported_candidates": 0, "imported_feedback": 0, "already_migrated": 0}),
            patch.object(goyathlay, "AuditStore", return_value=audit),
            patch.object(goyathlay, "ReputationEngine"),
            patch.object(goyathlay, "RbacEngine"),
            patch.object(goyathlay, "HostInventory"),
            patch.object(goyathlay, "ProfileManager", return_value=policies),
            patch.object(goyathlay, "CommandBlocklist"),
            patch.object(goyathlay, "MaintenanceManager", return_value=maintenance),
            patch.object(goyathlay, "PostgresConnectionManager", return_value=database_manager),
            patch.object(goyathlay, "SqliteProfileManager", return_value=Mock()),
            patch.object(goyathlay, "PostgresExecutor", return_value=executor),
            patch("builtins.input", side_effect=["db> prod show tables", "exit"]),
            redirect_stdout(output),
        ):
            goyathlay.main()

        provider_factory.assert_not_called()
        approval.review.assert_called_once_with(sql, display_command=False)
        executor.execute.assert_called_once()
        audit.append.assert_called_once()
        feedback_class.return_value.review.assert_called_once_with("show tables", sql, operator_view=True)
        self.assertIn("Profile: prod", output.getvalue())
        self.assertIn("Database: db01:5432/postgres", output.getvalue())
        self.assertIn("users", output.getvalue())

    def test_approved_database_query_executes_audits_and_collects_feedback(self):
        profile = DbProfile("prod", "db01", 5432, "postgres", "readonly")
        manager = Mock()
        manager.load_profile.return_value = profile
        approval = Mock()
        query = PostgresInterpreter().translate("show tables")
        approval.review.return_value = (True, query.sql)
        result = PostgresExecutionResult((("users", "public"),), ("table_name", "schema"), 1)
        executor_store = Mock()
        executor_store.execute.return_value = result
        audit_store = Mock()
        output = []

        with (
            patch.object(goyathlay, "PostgresExecutor", return_value=executor_store),
            patch.object(goyathlay, "AuditStore", return_value=audit_store),
            patch.object(goyathlay, "FeedbackManager") as feedback_class,
            patch("builtins.print", side_effect=output.append),
        ):
            handled, updated_audit = goyathlay._handle_database_prompt(
                "db> prod show tables", manager, approval, RiskEngine(), None
            )

        self.assertTrue(handled)
        self.assertIs(updated_audit, audit_store)
        approval.review.assert_called_once_with(query.sql, display_command=False)
        executor_store.execute.assert_called_once_with(query, profile)
        record = audit_store.append.call_args.args[0]
        self.assertIsInstance(record, AuditRecord)
        self.assertEqual(record.database_profile, "prod")
        self.assertEqual(record.host, "db01")
        self.assertEqual(record.command, query.sql)
        self.assertEqual(record.row_count, 1)
        self.assertTrue(record.success)
        feedback_class.return_value.review.assert_called_once_with("show tables", query.sql, operator_view=True)
        self.assertIn("Columns: table_name, schema", output)
        self.assertIn("users\tpublic", output)

    def test_invalid_sql_edit_is_blocked_before_postgres_executor(self):
        profile = DbProfile("prod", "db01", 5432, "postgres", "readonly")
        manager = Mock()
        manager.load_profile.return_value = profile
        approval = Mock()
        approval.review.return_value = (True, "DROP TABLE users")

        with (
            patch.object(goyathlay, "PostgresExecutor") as executor_class,
            patch("builtins.print"),
        ):
            handled, audit = goyathlay._handle_database_prompt(
                "db> prod show tables", manager, approval, RiskEngine(), None
            )

        self.assertTrue(handled)
        self.assertIsNone(audit)
        executor_class.assert_not_called()

    def test_database_profile_cli_switches_and_lists_profiles(self):
        manager = Mock()
        manager.list_profiles.return_value = [
            DbProfile("prod", "db01", 5432, "postgres", "readonly")
        ]
        manager.profile_store.default_name = "prod"
        manager.load_profile.return_value = manager.list_profiles.return_value[0]
        printed = []
        with patch("builtins.print", side_effect=printed.append):
            self.assertTrue(goyathlay._handle_db_profile_command("db profiles", manager))
            self.assertTrue(goyathlay._handle_db_profile_command("db profile prod", manager))
        manager.set_default_profile.assert_called_once_with("prod")
        self.assertIn("- prod: readonly@db01:5432/postgres (default)", printed)


if __name__ == "__main__":
    unittest.main()
