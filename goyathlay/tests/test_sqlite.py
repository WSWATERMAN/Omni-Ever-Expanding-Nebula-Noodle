"""Tests for deterministic SQLite intent translation."""

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from goyathlay.db import DatabaseQuery, QueryResult, UnsupportedIntentError
from goyathlay.db.sqlite import SqliteInterpreter
from goyathlay.db.sqlite_profiles import SqliteProfile
from goyathlay import goyathlay
from goyathlay.audit import AuditRecord
from goyathlay.risk import RiskEngine


class SqliteInterpreterTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = SqliteInterpreter()

    def test_show_tables_query(self):
        query = self.interpreter.translate("show tables")
        self.assertEqual(
            query.sql,
            """SELECT
    name
FROM sqlite_master
WHERE type='table'
ORDER BY name;""",
        )

    def test_show_schema_query(self):
        query = self.interpreter.translate("show schema")
        self.assertIn("type,", query.sql)
        self.assertIn("sql", query.sql)
        self.assertIn("sqlite_master", query.sql)

    def test_show_indexes_query(self):
        query = self.interpreter.translate("show indexes")
        self.assertIn("type='index'", query.sql)

    def test_sqlite_version_query(self):
        query = self.interpreter.translate("show sqlite version")
        self.assertEqual(query.sql, "SELECT sqlite_version() AS sqlite_version;")

    def test_show_views_and_triggers(self):
        self.assertIn("type='view'", self.interpreter.translate("show views").sql)
        self.assertIn("type='trigger'", self.interpreter.translate("show triggers").sql)

    def test_count_rows_in_table_quotes_identifier(self):
        query = self.interpreter.translate("count rows in table users")
        self.assertEqual(query.sql, 'SELECT COUNT(*) AS row_count FROM "users";')
        self.assertTrue(query.read_only)

    def test_all_supported_intents_translate_and_validate(self):
        intents = (
            "show tables", "show schema", "show indexes", "show table sizes",
            "count rows in table users", "show sqlite version", "show database size",
            "show foreign keys", "show triggers", "show views",
        )
        for intent in intents:
            with self.subTest(intent=intent):
                query = self.interpreter.translate(intent)
                self.assertIsInstance(query, DatabaseQuery)
                self.assertEqual(query.engine, "SQLite")
                self.assertTrue(query.read_only)
                self.assertTrue(self.interpreter.validate(query.sql).allowed)

    def test_unknown_intent_raises(self):
        with self.assertRaises(UnsupportedIntentError):
            self.interpreter.translate("drop all tables")

    def test_validator_rejects_sqlite_write_and_file_operations(self):
        for sql in (
            "INSERT INTO users VALUES (1)",
            "UPDATE users SET name='x'",
            "DELETE FROM users",
            "DROP TABLE users",
            "ALTER TABLE users ADD COLUMN x int",
            "ATTACH DATABASE 'other.db' AS other",
            "DETACH DATABASE other",
            "VACUUM",
            "PRAGMA writable_schema=ON",
        ):
            with self.subTest(sql=sql):
                self.assertFalse(self.interpreter.validate(sql).allowed)


class SqliteCliIntegrationTests(unittest.TestCase):
    def test_main_routes_sqlite_prompt_without_calling_ollama(self):
        profile = SqliteProfile("local", "/tmp/app.db")
        manager = Mock()
        manager.load_profile.return_value = profile
        manager.default_name = "local"
        sql = SqliteInterpreter().translate("show tables").sql
        approval = Mock()
        approval.review.return_value = (True, sql)
        executor = Mock()
        executor.execute.return_value = QueryResult(["name"], [("users",)], 1)
        maintenance = Mock()
        maintenance.is_allowed.return_value = True
        policies = Mock()
        policies.get_default_profile.return_value = goyathlay.PolicyProfile("development", True, True, 0)
        output = io.StringIO()

        with (
            patch.object(goyathlay, "_create_provider") as provider_factory,
            patch.object(goyathlay, "ApprovalManager", return_value=approval),
            patch.object(goyathlay, "ExecutionManager"),
            patch.object(goyathlay, "FeedbackManager"),
            patch.object(goyathlay, "CommandCache"),
            patch.object(goyathlay, "AuditStore"),
            patch.object(goyathlay, "ReputationEngine"),
            patch.object(goyathlay, "RbacEngine"),
            patch.object(goyathlay, "HostInventory"),
            patch.object(goyathlay, "FanoutExecutor"),
            patch.object(goyathlay, "ProfileManager", return_value=policies),
            patch.object(goyathlay, "CommandBlocklist"),
            patch.object(goyathlay, "MaintenanceManager", return_value=maintenance),
            patch.object(goyathlay, "PostgresConnectionManager", return_value=Mock()),
            patch.object(goyathlay, "SqliteProfileManager", return_value=manager),
            patch.object(goyathlay, "SqliteExecutor", return_value=executor),
            patch("builtins.input", side_effect=["sqlite> local show tables", "exit"]),
            redirect_stdout(output),
        ):
            goyathlay.main()

        provider_factory.assert_not_called()
        approval.review.assert_called_once_with(sql, display_command=False)
        executor.execute.assert_called_once_with(profile, sql)
        self.assertIn("Database:\n/tmp/app.db", output.getvalue())
        self.assertIn("users", output.getvalue())

    def test_approved_query_executes_audits_and_collects_feedback(self):
        profile = SqliteProfile("local", "/opt/app/data/app.db")
        manager = Mock()
        manager.load_profile.return_value = profile
        approval = Mock()
        query = SqliteInterpreter().translate("show tables")
        approval.review.return_value = (True, query.sql)
        result = QueryResult(["name"], [("users",)], 1)
        audit = Mock()
        output = io.StringIO()

        with (
            patch.object(goyathlay, "SqliteExecutor") as executor_class,
            patch.object(goyathlay, "AuditStore", return_value=audit),
            patch.object(goyathlay, "FeedbackManager") as feedback_class,
            redirect_stdout(output),
        ):
            executor_class.return_value.execute.return_value = result
            handled, updated_audit = goyathlay._handle_sqlite_prompt(
                "sqlite> local show tables", manager, approval, RiskEngine(), None
            )

        self.assertTrue(handled)
        self.assertIs(updated_audit, audit)
        approval.review.assert_called_once_with(query.sql, display_command=False)
        executor_class.return_value.execute.assert_called_once_with(profile, query.sql)
        record = audit.append.call_args.args[0]
        self.assertIsInstance(record, AuditRecord)
        self.assertEqual(record.database_engine, "sqlite")
        self.assertEqual(record.database_profile, "local")
        self.assertEqual(record.database_path, profile.database)
        self.assertEqual(record.row_count, 1)
        self.assertTrue(record.success)
        feedback_class.return_value.review.assert_called_once_with("show tables", query.sql)
        self.assertIn("Profile:\nlocal", output.getvalue())
        self.assertIn("users", output.getvalue())

    def test_invalid_edited_query_never_reaches_sqlite_executor(self):
        profile = SqliteProfile("local", "/opt/app/data/app.db")
        manager = Mock()
        manager.load_profile.return_value = profile
        approval = Mock()
        approval.review.return_value = (True, "ATTACH DATABASE 'x.db' AS x")
        output = io.StringIO()
        with (
            patch.object(goyathlay, "SqliteExecutor") as executor_class,
            redirect_stdout(output),
        ):
            handled, audit = goyathlay._handle_sqlite_prompt(
                "sqlite> local show tables", manager, approval, RiskEngine(), None
            )

        self.assertTrue(handled)
        self.assertIsNone(audit)
        executor_class.assert_not_called()
        self.assertIn("SQL validation blocked execution", output.getvalue())

    def test_sqlite_profile_cli_lists_and_switches_default(self):
        manager = Mock()
        manager.default_name = "local"
        manager.list_profiles.return_value = [SqliteProfile("local", "/var/lib/app.db")]
        manager.get_default_profile.return_value = manager.list_profiles.return_value[0]
        printed = []
        with patch("builtins.print", side_effect=printed.append):
            self.assertTrue(goyathlay._handle_sqlite_profile_command("sqlite profiles", manager))
            self.assertTrue(goyathlay._handle_sqlite_profile_command("sqlite profile local", manager))

        manager.set_default_profile.assert_called_once_with("local")
        self.assertIn("- local: /var/lib/app.db (default)", printed)


if __name__ == "__main__":
    unittest.main()
