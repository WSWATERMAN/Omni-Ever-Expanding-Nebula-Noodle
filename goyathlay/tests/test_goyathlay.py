import io
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from goyathlay import goyathlay
from goyathlay.execution import ExecutionError
from goyathlay.feedback import FeedbackResult
from goyathlay.cache.models import CachedCommand
from goyathlay.audit import AuditRecord
from goyathlay.reputation import CommandReputation
from goyathlay.rbac import AuthorizationDecision
from goyathlay.ssh.executor import SSHExecutionResult


class GoyathlayCliTests(unittest.TestCase):
    def run_cli(self, prompts, provider_result="netstat -tuln", approval_result=(True, "netstat -tuln"), execution_result=None, provider_error=None, execution_error=None, cache_entry=None, feedback_result=FeedbackResult.SUCCESS, reputation_result=None, authorization_result=AuthorizationDecision.ALLOW):
        provider = Mock()
        if provider_error:
            provider.generate_command.side_effect = provider_error
        else:
            provider.generate_command.return_value = provider_result

        approval_manager = Mock()
        approval_manager.review.return_value = approval_result
        execution_manager = Mock()
        if execution_error:
            execution_manager.execute.side_effect = execution_error
        else:
            execution_manager.execute.return_value = execution_result or subprocess.CompletedProcess(
                args=["netstat", "-tuln"], returncode=0, stdout="listening\n", stderr=""
            )
        feedback_manager = Mock()
        feedback_manager.review.return_value = feedback_result
        command_cache = Mock()
        command_cache.get_verified.return_value = cache_entry
        audit_store = Mock()
        reputation_engine = Mock()
        reputation_engine.get_reputation.return_value = reputation_result
        rbac_engine = Mock()
        rbac_engine.authorize.return_value = authorization_result

        output = io.StringIO()
        with (
            patch.object(goyathlay, "_create_provider", return_value=provider),
            patch.object(goyathlay, "ApprovalManager", return_value=approval_manager),
            patch.object(goyathlay, "ExecutionManager", return_value=execution_manager),
            patch.object(goyathlay, "FeedbackManager", return_value=feedback_manager),
            patch.object(goyathlay, "CommandCache", return_value=command_cache),
            patch.object(goyathlay, "AuditStore", return_value=audit_store),
            patch.object(goyathlay, "ReputationEngine", return_value=reputation_engine),
            patch.object(goyathlay, "RbacEngine", return_value=rbac_engine),
            patch.object(goyathlay, "clean_command", wraps=goyathlay.clean_command) as cleaner,
            patch("builtins.input", side_effect=prompts) as mocked_input,
            redirect_stdout(output),
        ):
            goyathlay.main()

        return output.getvalue(), provider, cleaner, approval_manager, execution_manager, mocked_input, feedback_manager, command_cache, audit_store, reputation_engine

    def test_successful_path_cleans_approves_and_executes(self):
        output, provider, cleaner, approval, execution, _, feedback, cache, audit, reputation = self.run_cli(
            ["show listening ports", "exit"],
            provider_result="```bash\nnetstat -tuln\n```",
        )

        provider.generate_command.assert_called_once_with("show listening ports")
        cleaner.assert_called_once_with("```bash\nnetstat -tuln\n```")
        approval.review.assert_called_once_with("netstat -tuln", display_command=False)
        execution.execute.assert_called_once_with("netstat -tuln")
        feedback.review.assert_called_once_with("show listening ports", "netstat -tuln")
        cache.record_success.assert_called_once_with("show listening ports", "netstat -tuln")
        audit_record = audit.append.call_args.args[0]
        self.assertIsInstance(audit_record, AuditRecord)
        self.assertEqual(audit_record.intent, "show listening ports")
        self.assertEqual(audit_record.command, "netstat -tuln")
        self.assertEqual(audit_record.risk_level, "LOW")
        self.assertEqual(audit_record.approval_result, "approved")
        self.assertEqual(audit_record.return_code, 0)
        self.assertTrue(audit_record.success)
        reputation.get_reputation.assert_called_once_with("netstat -tuln")
        self.assertIn("Policy:\nALLOW", output)
        self.assertIn("Return Code: 0", output)
        self.assertIn("STDOUT:\nlistening", output)

    def test_cancel_does_not_execute(self):
        output, _, _, approval, execution, _, feedback, cache, audit, _ = self.run_cli(
            ["show listening ports", "exit"], approval_result=(False, None)
        )

        approval.review.assert_called_once_with("netstat -tuln", display_command=False)
        execution.execute.assert_not_called()
        feedback.review.assert_not_called()
        cache.record_success.assert_not_called()
        audit.append.assert_not_called()
        self.assertIn("Command cancelled.", output)

    def test_generation_failure_is_reported_and_loop_continues(self):
        output, provider, _, _, execution, mocked_input, feedback, cache, audit, _ = self.run_cli(
            ["show listening ports", "quit"], provider_error=RuntimeError("Ollama unavailable")
        )

        self.assertIn("Unable to generate command:\nOllama unavailable", output)
        provider.generate_command.assert_called_once_with("show listening ports")
        self.assertEqual(mocked_input.call_count, 2)
        execution.execute.assert_not_called()
        feedback.review.assert_not_called()
        cache.get_verified.assert_called_once_with("show listening ports")
        audit.append.assert_not_called()

    def test_execution_failure_is_reported_and_loop_continues(self):
        output, _, _, _, execution, mocked_input, feedback, cache, audit, _ = self.run_cli(
            ["show listening ports", "exit"], execution_error=ExecutionError("Command not found")
        )

        execution.execute.assert_called_once_with("netstat -tuln")
        self.assertIn("Execution failed:\nCommand not found", output)
        self.assertEqual(mocked_input.call_count, 2)
        feedback.review.assert_not_called()
        cache.record_success.assert_not_called()
        audit_record = audit.append.call_args.args[0]
        self.assertEqual(audit_record.return_code, -1)
        self.assertFalse(audit_record.success)

    def test_keyboard_interrupt_exits_gracefully(self):
        output, _, _, _, execution, _, feedback, cache, audit, _ = self.run_cli([KeyboardInterrupt()])

        self.assertIn("Exiting Goyathlay.", output)
        execution.execute.assert_not_called()
        feedback.review.assert_not_called()
        cache.get_verified.assert_not_called()
        audit.append.assert_not_called()

    def test_verified_cache_hit_skips_provider_and_uses_approval(self):
        output, provider, _, approval, execution, _, feedback, cache, audit, _ = self.run_cli(
            ["show listening ports", "Y", "exit"],
            cache_entry=CachedCommand(
                "show listening ports", "netstat -tuln", "verified", "2026-10-31T12:00:00Z"
            ),
        )

        provider.generate_command.assert_not_called()
        approval.review.assert_called_once_with("netstat -tuln", display_command=False)
        execution.execute.assert_called_once_with("netstat -tuln")
        feedback.review.assert_called_once_with("show listening ports", "netstat -tuln")
        self.assertIn("Verified command found.", output)

    def test_cache_decline_falls_back_to_provider(self):
        _, provider, _, _, _, _, _, _, _, _ = self.run_cli(
            ["show listening ports", "N", "exit"],
            cache_entry=CachedCommand(
                "show listening ports", "netstat -tuln", "verified", "2026-10-31T12:00:00Z"
            ),
        )

        provider.generate_command.assert_called_once_with("show listening ports")

    def test_feedback_failure_and_dangerous_update_cache(self):
        for feedback_result, method in (
            (FeedbackResult.FAILURE, "record_failure"),
            (FeedbackResult.DANGEROUS, "record_dangerous"),
        ):
            with self.subTest(feedback_result=feedback_result):
                _, _, _, _, _, _, _, cache, _, _ = self.run_cli(
                    ["show listening ports", "exit"], feedback_result=feedback_result
                )
                getattr(cache, method).assert_called_once_with("show listening ports", "netstat -tuln")

    def test_high_risk_executes_only_after_exact_execute_confirmation(self):
        output, _, _, approval, execution, _, _, _, audit, _ = self.run_cli(
            ["remove temp files", "EXECUTE", "OVERRIDE", "exit"],
            provider_result="rm -rf /tmp/test",
            approval_result=(True, "rm -rf /tmp/test"),
        )

        self.assertIn("Risk Level:\nHIGH", output)
        approval.review.assert_called_once_with("rm -rf /tmp/test", display_command=False)
        execution.execute.assert_called_once_with("rm -rf /tmp/test")
        self.assertTrue(audit.append.call_args.args[0].success)

    def test_high_risk_is_cancelled_without_exact_execute_confirmation(self):
        output, _, _, approval, execution, _, feedback, cache, audit, _ = self.run_cli(
            ["remove temp files", "execute", "exit"],
            provider_result="rm -rf /tmp/test",
        )

        self.assertIn("High-risk command cancelled.", output)
        approval.review.assert_not_called()
        execution.execute.assert_not_called()
        feedback.review.assert_not_called()
        cache.record_success.assert_not_called()
        audit.append.assert_not_called()

    def test_policy_denies_high_risk_with_very_poor_reputation(self):
        output, _, _, approval, execution, _, _, _, audit, _ = self.run_cli(
            ["remove temp files", "exit"],
            provider_result="rm -rf /tmp/test",
            reputation_result=CommandReputation("rm -rf /tmp/test", 0, 1, 1, 0.0),
        )

        self.assertIn("Policy:\nDENY", output)
        self.assertIn("Execution blocked.", output)
        approval.review.assert_not_called()
        execution.execute.assert_not_called()
        audit.append.assert_not_called()

    def test_policy_override_allows_medium_risk_to_reach_approval(self):
        output, _, _, approval, execution, _, _, _, _, _ = self.run_cli(
            ["restart nginx", "OVERRIDE", "exit"],
            provider_result="systemctl restart nginx",
            approval_result=(True, "systemctl restart nginx"),
        )

        self.assertIn("Policy:\nREQUIRE EXTRA CONFIRMATION", output)
        approval.review.assert_called_once_with("systemctl restart nginx", display_command=False)
        execution.execute.assert_called_once_with("systemctl restart nginx")

    def test_policy_override_cancellation_blocks_execution(self):
        output, _, _, approval, execution, _, _, _, audit, _ = self.run_cli(
            ["restart nginx", "no", "exit"],
            provider_result="systemctl restart nginx",
        )

        self.assertIn("Policy override cancelled.", output)
        approval.review.assert_not_called()
        execution.execute.assert_not_called()
        audit.append.assert_not_called()

    def test_high_risk_edit_requires_confirmation_for_final_command(self):
        output, _, _, approval, execution, _, _, _, audit, _ = self.run_cli(
            ["remove temp files", "EXECUTE", "OVERRIDE", "exit"],
            provider_result="ls /tmp",
            approval_result=(True, "rm -rf /tmp/test"),
        )

        approval.review.assert_called_once_with("ls /tmp", display_command=False)
        execution.execute.assert_called_once_with("rm -rf /tmp/test")
        audit_record = audit.append.call_args.args[0]
        self.assertEqual(audit_record.command, "rm -rf /tmp/test")
        self.assertEqual(audit_record.risk_level, "HIGH")
        self.assertTrue(audit_record.success)
        self.assertIn("Generated Command:\nrm -rf /tmp/test", output)

    def test_high_risk_edit_without_confirmation_is_not_executed_or_logged(self):
        output, _, _, _, execution, _, _, _, audit, _ = self.run_cli(
            ["remove temp files", "no", "exit"],
            provider_result="ls /tmp",
            approval_result=(True, "rm -rf /tmp/test"),
        )

        self.assertIn("High-risk command cancelled.", output)
        execution.execute.assert_not_called()
        audit.append.assert_not_called()

    def test_skipped_feedback_does_not_update_cache(self):
        _, _, _, _, _, _, _, cache, _, _ = self.run_cli(
            ["show listening ports", "exit"], feedback_result=FeedbackResult.SKIPPED
        )

        cache.record_success.assert_not_called()
        cache.record_failure.assert_not_called()
        cache.record_dangerous.assert_not_called()

    def test_remote_prompt_uses_ssh_after_approval_and_scopes_cache(self):
        provider = Mock()
        provider.generate_command.return_value = "netstat -tuln"
        approval = Mock()
        approval.review.return_value = (True, "netstat -tuln")
        local_execution = Mock()
        ssh_client = Mock()
        connector = Mock()
        connector.connect.return_value = ssh_client
        ssh_executor = Mock()
        ssh_executor.execute.return_value = SSHExecutionResult("ports\n", "", 0)
        feedback = Mock()
        feedback.review.return_value = FeedbackResult.SUCCESS
        cache = Mock()
        cache.get_verified.return_value = None
        audit = Mock()
        reputation = Mock()
        reputation.get_reputation.return_value = None
        output = io.StringIO()

        with (
            patch.object(goyathlay, "_create_provider", return_value=provider),
            patch.object(goyathlay, "ApprovalManager", return_value=approval),
            patch.object(goyathlay, "ExecutionManager", return_value=local_execution),
            patch.object(goyathlay, "FeedbackManager", return_value=feedback),
            patch.object(goyathlay, "CommandCache", return_value=cache),
            patch.object(goyathlay, "AuditStore", return_value=audit),
            patch.object(goyathlay, "ReputationEngine", return_value=reputation),
            patch.object(goyathlay, "SSHConnector", return_value=connector),
            patch.object(goyathlay, "SSHExecutor", return_value=ssh_executor),
            patch.object(goyathlay.getpass, "getuser", return_value="scott"),
            patch("builtins.input", side_effect=["remote> server01 show listening ports", "exit"]),
            redirect_stdout(output),
        ):
            goyathlay.main()

        connector.connect.assert_called_once_with("server01", username="scott")
        ssh_executor.execute.assert_called_once_with(ssh_client, "netstat -tuln")
        ssh_client.close.assert_called_once()
        local_execution.execute.assert_not_called()
        feedback.review.assert_called_once_with(
            "remote:server01 show listening ports", "netstat -tuln"
        )
        cache.record_success.assert_called_once_with(
            "remote:server01 show listening ports", "netstat -tuln"
        )
        self.assertEqual(audit.append.call_args.args[0].intent, "remote:server01 show listening ports")
        self.assertIn("STDOUT:\nports", output.getvalue())

    def test_role_override_is_required_before_other_high_risk_checks(self):
        output, _, _, approval, execution, mocked_input, _, _, audit, _ = self.run_cli(
            ["remove temp files", "ROLE-OVERRIDE", "EXECUTE", "OVERRIDE", "exit"],
            provider_result="rm -rf /tmp/test",
            approval_result=(True, "rm -rf /tmp/test"),
            authorization_result=AuthorizationDecision.REQUIRE_OVERRIDE,
        )

        self.assertIn("Authorization:\nREQUIRE_OVERRIDE", output)
        self.assertIn("Type ROLE-OVERRIDE to continue:", str(mocked_input.call_args_list))
        approval.review.assert_called_once()
        execution.execute.assert_called_once()
        audit.append.assert_called_once()

    def test_role_override_cancellation_blocks_execution(self):
        output, _, _, approval, execution, _, _, _, audit, _ = self.run_cli(
            ["remove temp files", "no", "exit"],
            provider_result="rm -rf /tmp/test",
            authorization_result=AuthorizationDecision.REQUIRE_OVERRIDE,
        )

        self.assertIn("Role override cancelled.", output)
        approval.review.assert_not_called()
        execution.execute.assert_not_called()
        audit.append.assert_not_called()


if __name__ == "__main__":
    unittest.main()
