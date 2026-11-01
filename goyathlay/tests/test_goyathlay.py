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
from goyathlay.inventory import HostRecord, InventoryError
from goyathlay.fanout import HostExecutionResult
from goyathlay.profiles import PolicyProfile


class GoyathlayCliTests(unittest.TestCase):
    def run_cli(self, prompts, provider_result="netstat -tuln", approval_result=(True, "netstat -tuln"), execution_result=None, provider_error=None, execution_error=None, cache_entry=None, feedback_result=FeedbackResult.SUCCESS, reputation_result=None, authorization_result=AuthorizationDecision.ALLOW, inventory_targets=None, fanout_results=None, profile_name="staging", blocked_rule=None, blocked_rules_by_command=None):
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
        inventory = Mock()
        inventory.resolve_target.return_value = inventory_targets or []
        fanout_executor = Mock()
        fanout_executor.execute.return_value = fanout_results or []
        profiles = {
            "development": PolicyProfile("development", True, True, 0),
            "staging": PolicyProfile("staging", True, True, 25),
            "production": PolicyProfile("production", False, False, 50),
            "emergency": PolicyProfile("emergency", True, True, 0),
        }
        profile_manager = Mock()
        profile_manager.get_default_profile.return_value = profiles[profile_name]
        profile_manager.list_profiles.return_value = list(profiles.values())
        profile_manager.load_profile.side_effect = profiles.__getitem__
        profile_manager.get_profile_for_host.side_effect = lambda host: profiles.get(host, profiles[profile_name])
        maintenance_manager = Mock()
        maintenance_manager.enabled = False
        maintenance_manager.list_windows.return_value = []
        maintenance_manager.is_allowed.return_value = True
        database_manager = Mock()
        command_blocklist = Mock()
        command_blocklist.list_commands.return_value = ["rm -rf /", "mkfs", "dd if="]
        if blocked_rules_by_command is not None:
            command_blocklist.blocked_by.side_effect = blocked_rules_by_command.get
        else:
            command_blocklist.blocked_by.return_value = blocked_rule
        command_blocklist.is_blocked.side_effect = lambda command: command_blocklist.blocked_by(command) is not None

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
            patch.object(goyathlay, "HostInventory", return_value=inventory),
            patch.object(goyathlay, "FanoutExecutor", return_value=fanout_executor),
            patch.object(goyathlay, "ProfileManager", return_value=profile_manager),
            patch.object(goyathlay, "MaintenanceManager", return_value=maintenance_manager),
            patch.object(goyathlay, "PostgresConnectionManager", return_value=database_manager),
            patch.object(goyathlay, "SqliteProfileManager", return_value=Mock()),
            patch.object(goyathlay, "MssqlProfileManager", return_value=Mock()),
            patch.object(goyathlay, "CommandBlocklist", return_value=command_blocklist),
            patch.object(goyathlay, "clean_command", wraps=goyathlay.clean_command) as cleaner,
            patch("builtins.input", side_effect=prompts) as mocked_input,
            redirect_stdout(output),
        ):
            goyathlay.main()

        return output.getvalue(), provider, cleaner, approval_manager, execution_manager, mocked_input, feedback_manager, command_cache, audit_store, reputation_engine

    def test_dryrun_builds_plan_without_approval_or_execution(self):
        output, provider, _, approval, execution, _, _, _, _, _ = self.run_cli(
            ["dryrun> show listening ports", "exit"]
        )
        provider.generate_command.assert_called_once_with("show listening ports")
        approval.review.assert_not_called()
        execution.execute.assert_not_called()
        self.assertIn("DRY RUN", output)
        self.assertIn("Risk:", output)
        self.assertIn("Targets:", output)

    def test_maintenance_cli_lists_adds_and_removes_windows(self):
        manager = Mock()
        manager.enabled = False
        manager.list_windows.return_value = [
            goyathlay.MaintenanceWindow("production", ["SAT", "SUN"], "01:00", "05:00")
        ]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(goyathlay._handle_maintenance_command("maintenance", manager))
            self.assertTrue(goyathlay._handle_maintenance_command("maintenance enable", manager))
            self.assertTrue(
                goyathlay._handle_maintenance_command(
                    "maintenance add production SAT,SUN 01:00 05:00", manager
                )
            )
            self.assertTrue(goyathlay._handle_maintenance_command("maintenance remove production", manager))

        manager.set_enabled.assert_called_once_with(True)
        manager.add_window.assert_called_once_with(
            goyathlay.MaintenanceWindow("production", ["SAT", "SUN"], "01:00", "05:00")
        )
        manager.remove_window.assert_called_once_with("production")
        self.assertIn("production: SAT,SUN 01:00-05:00", output.getvalue())

    def test_maintenance_block_stops_before_blocklist_and_approval(self):
        provider = Mock()
        provider.generate_command.return_value = "ls -la"
        approval = Mock()
        execution = Mock()
        maintenance = Mock()
        maintenance.is_allowed.return_value = False
        blocklist = Mock()
        blocklist.blocked_by.return_value = None
        output = io.StringIO()
        with (
            patch.object(goyathlay, "_create_provider", return_value=provider),
            patch.object(goyathlay, "ApprovalManager", return_value=approval),
            patch.object(goyathlay, "ExecutionManager", return_value=execution),
            patch.object(goyathlay, "FeedbackManager"),
            patch.object(goyathlay, "CommandCache"),
            patch.object(goyathlay, "AuditStore"),
            patch.object(goyathlay, "ReputationEngine"),
            patch.object(goyathlay, "RbacEngine"),
            patch.object(goyathlay, "HostInventory"),
            patch.object(goyathlay, "ProfileManager") as profiles,
            patch.object(goyathlay, "MaintenanceManager", return_value=maintenance),
            patch.object(goyathlay, "PostgresConnectionManager", return_value=Mock()),
            patch.object(goyathlay, "SqliteProfileManager", return_value=Mock()),
            patch.object(goyathlay, "MssqlProfileManager", return_value=Mock()),
            patch.object(goyathlay, "CommandBlocklist", return_value=blocklist),
            patch("builtins.input", side_effect=["show files", "exit"]),
            redirect_stdout(output),
        ):
            profiles.return_value.get_default_profile.return_value = PolicyProfile("production", False, False, 50)
            goyathlay.main()

        self.assertIn("Execution Blocked", output.getvalue())
        self.assertIn("Outside approved maintenance window", output.getvalue())
        blocklist.blocked_by.assert_not_called()
        approval.review.assert_not_called()
        execution.execute.assert_not_called()

    def test_maintenance_window_is_rechecked_after_approval(self):
        provider = Mock()
        provider.generate_command.return_value = "ls -la"
        approval = Mock()
        approval.review.return_value = (True, "ls -la")
        execution = Mock()
        maintenance = Mock()
        maintenance.is_allowed.side_effect = [True, False]
        output = io.StringIO()
        with (
            patch.object(goyathlay, "_create_provider", return_value=provider),
            patch.object(goyathlay, "ApprovalManager", return_value=approval),
            patch.object(goyathlay, "ExecutionManager", return_value=execution),
            patch.object(goyathlay, "FeedbackManager"),
            patch.object(goyathlay, "CommandCache") as cache_class,
            patch.object(goyathlay, "AuditStore"),
            patch.object(goyathlay, "ReputationEngine") as reputation_class,
            patch.object(goyathlay, "RbacEngine"),
            patch.object(goyathlay, "HostInventory"),
            patch.object(goyathlay, "ProfileManager") as profiles,
            patch.object(goyathlay, "MaintenanceManager", return_value=maintenance),
            patch.object(goyathlay, "PostgresConnectionManager", return_value=Mock()),
            patch.object(goyathlay, "SqliteProfileManager", return_value=Mock()),
            patch.object(goyathlay, "MssqlProfileManager", return_value=Mock()),
            patch.object(goyathlay, "CommandBlocklist") as blocklist_class,
            patch("builtins.input", side_effect=["show files", "exit"]),
            redirect_stdout(output),
        ):
            profiles.return_value.get_default_profile.return_value = PolicyProfile("production", False, False, 50)
            blocklist_class.return_value.blocked_by.return_value = None
            cache_class.return_value.get_verified.return_value = None
            reputation_class.return_value.get_reputation.return_value = None
            goyathlay.main()

        self.assertEqual(maintenance.is_allowed.call_count, 2)
        approval.review.assert_called_once()
        execution.execute.assert_not_called()
        self.assertIn("Outside approved maintenance window", output.getvalue())

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

    def test_blocked_command_stops_before_approval_and_execution(self):
        output, _, _, approval, execution, _, feedback, cache, audit, _ = self.run_cli(
            ["remove temporary files", "exit"],
            provider_result="rm -rf /tmp/test",
            blocked_rule="rm -rf *",
        )

        self.assertIn(
            "Execution Blocked\nRule:\nrm -rf *\nCommand:\nrm -rf /tmp/test",
            output,
        )
        approval.review.assert_not_called()
        execution.execute.assert_not_called()
        feedback.review.assert_not_called()
        cache.record_success.assert_not_called()
        audit.append.assert_not_called()

    def test_edited_command_is_rechecked_against_blocklist(self):
        output, _, _, approval, execution, _, feedback, _, audit, _ = self.run_cli(
            ["show files", "exit"],
            provider_result="ls -la",
            approval_result=(True, "rm -rf /tmp/test"),
            blocked_rules_by_command={"rm -rf /tmp/test": "rm -rf *"},
        )

        self.assertIn("Rule:\nrm -rf *\nCommand:\nrm -rf /tmp/test", output)
        approval.review.assert_called_once()
        execution.execute.assert_not_called()
        feedback.review.assert_not_called()
        audit.append.assert_not_called()

    def test_blocklist_cli_lists_adds_and_removes_rules(self):
        manager = Mock()
        manager.list_commands.return_value = ["rm -rf /", "mkfs"]
        manager.add.return_value = True
        manager.remove.return_value = True
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(goyathlay._handle_blocklist_command("blocklist", manager))
            self.assertTrue(goyathlay._handle_blocklist_command('block add "rm -rf *"', manager))
            self.assertTrue(goyathlay._handle_blocklist_command('block remove "rm -rf *"', manager))

        self.assertIn("Blocked Commands:\n- rm -rf /\n- mkfs", output.getvalue())
        manager.add.assert_called_once_with("rm -rf *")
        manager.remove.assert_called_once_with("rm -rf *")

    def test_profile_command_switches_active_policy(self):
        output, _, _, _, _, _, _, _, _, _ = self.run_cli(
            ["profile development", "show listening ports", "exit"],
        )

        self.assertIn("Current Profile: development", output)
        self.assertIn("Profile:\ndevelopment", output)

    def test_profiles_command_lists_available_profiles(self):
        output, *_ = self.run_cli(["profiles", "exit"])

        self.assertIn(
            "Available Profiles:\n- development\n- staging\n- production\n- emergency",
            output,
        )

    def test_production_profile_blocks_high_risk_before_approval(self):
        output, _, _, approval, execution, _, _, _, audit, _ = self.run_cli(
            ["remove temp files", "exit"],
            provider_result="rm -rf /tmp/test",
            profile_name="production",
        )

        self.assertIn("Profile:\nproduction", output)
        self.assertIn("Decision:\nDENY", output)
        self.assertIn("Production profile blocks high-risk commands", output)
        approval.review.assert_not_called()
        execution.execute.assert_not_called()
        audit.append.assert_not_called()

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
            profile_name="production",
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
        inventory = Mock()
        inventory.resolve_target.return_value = [
            HostRecord("server01", "server01.example", 2222, "ubuntu")
        ]
        profile_manager = Mock()
        profile_manager.get_default_profile.return_value = PolicyProfile("staging", True, True, 25)
        profile_manager.get_profile_for_host.return_value = PolicyProfile("staging", True, True, 25)
        maintenance_manager = Mock()
        maintenance_manager.is_allowed.return_value = True
        command_blocklist = Mock()
        command_blocklist.blocked_by.return_value = None
        output = io.StringIO()

        with (
            patch.object(goyathlay, "_create_provider", return_value=provider),
            patch.object(goyathlay, "ApprovalManager", return_value=approval),
            patch.object(goyathlay, "ExecutionManager", return_value=local_execution),
            patch.object(goyathlay, "FeedbackManager", return_value=feedback),
            patch.object(goyathlay, "CommandCache", return_value=cache),
            patch.object(goyathlay, "AuditStore", return_value=audit),
            patch.object(goyathlay, "ReputationEngine", return_value=reputation),
            patch.object(goyathlay, "HostInventory", return_value=inventory),
            patch.object(goyathlay, "ProfileManager", return_value=profile_manager),
            patch.object(goyathlay, "MaintenanceManager", return_value=maintenance_manager),
            patch.object(goyathlay, "PostgresConnectionManager", return_value=Mock()),
            patch.object(goyathlay, "SqliteProfileManager", return_value=Mock()),
            patch.object(goyathlay, "MssqlProfileManager", return_value=Mock()),
            patch.object(goyathlay, "CommandBlocklist", return_value=command_blocklist),
            patch.object(goyathlay, "SSHConnector", return_value=connector),
            patch.object(goyathlay, "SSHExecutor", return_value=ssh_executor),
            patch("builtins.input", side_effect=["remote> server01 show listening ports", "exit"]),
            redirect_stdout(output),
        ):
            goyathlay.main()

        connector.connect.assert_called_once_with(
            "server01.example", username="ubuntu", port=2222
        )
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
        self.assertIn("Targets:\n- server01", output.getvalue())
        self.assertIn("STDOUT:\nports", output.getvalue())

    def test_group_fanout_aggregates_and_audits_each_host_with_one_feedback(self):
        first = HostRecord("server01", "server01.example", 22, "ubuntu")
        second = HostRecord("server02", "server02.example", 22, "ubuntu")
        output, provider, _, approval, execution, _, feedback, cache, audit, _ = self.run_cli(
            ["remote> prod show listening ports", "exit"],
            inventory_targets=[first, second],
            fanout_results=[
                HostExecutionResult("server01", 0, "ports\n", "", True),
                HostExecutionResult("server02", 255, "", "connection failed", False),
            ],
        )

        self.assertIn("Targets:\n- server01\n- server02", output)
        self.assertIn("Host: server01\nSuccess: True", output)
        self.assertIn("Host: server02\nSuccess: False\nExit Code: 255", output)
        self.assertIn("Summary:\n2 Hosts\n1 Success\n1 Failure", output)
        provider.generate_command.assert_called_once_with("show listening ports")
        approval.review.assert_called_once_with("netstat -tuln", display_command=False)
        execution.execute.assert_not_called()
        audit_records = [call.args[0] for call in audit.append.call_args_list]
        self.assertEqual([record.host for record in audit_records], ["server01", "server02"])
        self.assertEqual([record.success for record in audit_records], [True, False])
        feedback.review.assert_called_once_with("remote:prod show listening ports", "netstat -tuln")
        cache.record_success.assert_not_called()

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
