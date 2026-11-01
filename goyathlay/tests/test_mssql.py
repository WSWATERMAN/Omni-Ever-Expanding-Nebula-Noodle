"""Tests for fixed MSSQL inspection intent translations."""

import unittest
from unittest.mock import Mock, patch

from goyathlay import goyathlay
from goyathlay.db.mssql import MssqlInterpreter
from goyathlay.db.base import UnsupportedIntentError
from goyathlay.db.mssql_executor import MssqlQueryResult
from goyathlay.db.mssql_profiles import MssqlProfile


class MssqlInterpreterTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = MssqlInterpreter()

    def test_supported_intents_translate_to_read_only_queries(self):
        intents = (
            "show databases", "show tables", "show active sessions",
            "show blocking locks", "show index usage", "show database size",
        )
        for intent in intents:
            with self.subTest(intent=intent):
                query = self.interpreter.translate(intent)
                self.assertEqual(query.engine, "MSSQL")
                self.assertTrue(query.read_only)
                self.assertTrue(self.interpreter.validate(query.sql).allowed)

    def test_show_databases(self):
        self.assertIn("sys.databases", self.interpreter.translate("show databases").sql)

    def test_show_tables(self):
        self.assertIn("sys.tables", self.interpreter.translate("show tables").sql)

    def test_show_active_sessions(self):
        self.assertIn("sys.dm_exec_requests", self.interpreter.translate("show active sessions").sql)

    def test_show_blocking_locks(self):
        sql = self.interpreter.translate("show blocking locks").sql
        self.assertIn("sys.dm_tran_locks", sql)
        self.assertIn("request_status = 'WAIT'", sql)

    def test_show_index_usage_and_database_size(self):
        self.assertIn("sys.dm_db_index_usage_stats", self.interpreter.translate("show index usage").sql)
        self.assertIn("sys.database_files", self.interpreter.translate("show database size").sql)

    def test_unknown_intent_is_rejected(self):
        with self.assertRaises(UnsupportedIntentError):
            self.interpreter.translate("drop database")

    def test_cli_approves_executes_and_audits_mssql_query(self):
        manager = Mock()
        manager.load_profile.return_value = MssqlProfile("prod", "sql01", "inventory", "readonly")
        approval = Mock()
        approval.review.return_value = (True, "SELECT name FROM sys.databases ORDER BY name;")
        risk = Mock()
        risk.assess.return_value.level.name = "LOW"
        executor = Mock()
        executor.execute.return_value = MssqlQueryResult(["name"], [("inventory",)], 1)
        audit = Mock()

        with (
            patch.object(goyathlay, "MssqlExecutor", return_value=executor),
            patch.object(goyathlay, "FeedbackManager"),
            patch.object(goyathlay, "_append_database_audit", return_value=audit) as append_audit,
            patch("builtins.print"),
        ):
            handled, returned_audit = goyathlay._handle_mssql_prompt(
                "mssql> prod show databases", manager, approval, risk, None
            )

        self.assertTrue(handled)
        self.assertIs(returned_audit, audit)
        approval.review.assert_called_once()
        executor.execute.assert_called_once()
        self.assertEqual(append_audit.call_args.kwargs["engine"], "mssql")
        self.assertEqual(append_audit.call_args.kwargs["host"], "sql01")


if __name__ == "__main__":
    unittest.main()
