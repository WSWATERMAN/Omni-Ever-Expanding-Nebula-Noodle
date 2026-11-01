#!/usr/bin/env python3
"""Interactive, local-first Goyathlay command line application."""

import shlex
from datetime import datetime

if __package__:
    from .approval import ApprovalManager
    from .command_cleaner import clean_command
    from .execution import ExecutionError, ExecutionManager
    from .feedback import FeedbackManager, FeedbackStoreError
    from .feedback import FeedbackResult
    from .cache import CacheError, CommandCache
    from .risk import RiskEngine, RiskLevel
    from .audit import AuditRecord, AuditStore, AuditStoreError, utc_timestamp
    from .reputation import CommandReputation, ReputationEngine
    from .policy import PolicyDecision, PolicyEngine, PolicyResult
    from .rbac import AuthorizationDecision, RbacEngine, Role, UserContext
    from .ssh.connector import SSHConnectionError, SSHConnector
    from .ssh.executor import SSHExecutionError, SSHExecutor
    from .inventory import HostInventory, InventoryError
    from .fanout import FanoutExecutor, HostExecutionResult
    from .profiles import PolicyProfile, ProfileManager, ProfileNotFoundError, ProfileStoreError
    from .blocklist import BlocklistError, CommandBlocklist
    from .maintenance import MaintenanceError, MaintenanceManager, MaintenanceWindow
else:  # Support: python goyathlay/goyathlay.py
    from approval import ApprovalManager
    from command_cleaner import clean_command
    from execution import ExecutionError, ExecutionManager
    from feedback import FeedbackManager, FeedbackStoreError
    from feedback import FeedbackResult
    from cache import CacheError, CommandCache
    from risk import RiskEngine, RiskLevel
    from audit import AuditRecord, AuditStore, AuditStoreError, utc_timestamp
    from reputation import CommandReputation, ReputationEngine
    from policy import PolicyDecision, PolicyEngine, PolicyResult
    from rbac import AuthorizationDecision, RbacEngine, Role, UserContext
    from ssh.connector import SSHConnectionError, SSHConnector
    from ssh.executor import SSHExecutionError, SSHExecutor
    from inventory import HostInventory, InventoryError
    from fanout import FanoutExecutor, HostExecutionResult
    from profiles import PolicyProfile, ProfileManager, ProfileNotFoundError, ProfileStoreError
    from blocklist import BlocklistError, CommandBlocklist
    from maintenance import MaintenanceError, MaintenanceManager, MaintenanceWindow


def _create_provider():
    """Load the Ollama provider only when a prompt needs generation."""
    if __package__:
        from .providers.ollama_provider import OllamaProvider
    else:
        from providers.ollama_provider import OllamaProvider
    return OllamaProvider()


def _confirm_cached_command(intent: str, command: str) -> bool:
    """Ask whether to use a verified command instead of querying Ollama."""
    print("Verified command found.")
    print(f"Intent:\n{intent}")
    print(f"Command:\n{command}")
    print("Use cached command?")
    print("[Y] Yes")
    print("[N] No")
    while True:
        choice = input("Selection: ").strip().casefold()
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no"):
            return False
        print("Please enter Y (Yes) or N (No).")


def _confirm_high_risk() -> bool:
    """Require the exact confirmation word before high-risk approval."""
    return input("Type EXECUTE to continue: ").strip() == "EXECUTE"


def _confirm_policy_override() -> bool:
    """Require an explicit override for policy decisions needing confirmation."""
    return input("Type OVERRIDE to continue: ").strip() == "OVERRIDE"


def _confirm_role_override() -> bool:
    """Require the role-specific confirmation before continuing."""
    return input("Type ROLE-OVERRIDE to continue: ").strip() == "ROLE-OVERRIDE"


def _handle_blocklist_command(raw_command: str, blocklist: CommandBlocklist | None) -> bool:
    """Handle local blocklist management commands; return if recognized."""
    stripped = raw_command.strip()
    if stripped.casefold() == "blocklist":
        if blocklist is None:
            print("Command blocklist is unavailable.")
            return True
        print("Blocked Commands:")
        for command in blocklist.list_commands():
            print(f"- {command}")
        return True
    if not stripped.casefold().startswith("block "):
        return False
    if blocklist is None:
        print("Command blocklist is unavailable.")
        return True
    try:
        parts = shlex.split(stripped)
    except ValueError as exc:
        print(f"Invalid blocklist command: {exc}")
        return True
    if len(parts) != 3 or parts[0].casefold() != "block" or parts[1].casefold() not in ("add", "remove"):
        print('Usage: block add "COMMAND" | block remove "COMMAND"')
        return True
    try:
        if parts[1].casefold() == "add":
            added = blocklist.add(parts[2])
            print("Block rule added." if added else "Block rule already exists.")
        else:
            removed = blocklist.remove(parts[2])
            print("Block rule removed." if removed else "Block rule not found.")
    except (BlocklistError, ValueError) as exc:
        print(f"Unable to update blocklist:\n{exc}")
    return True


def _display_blocked_command(rule: str, command: str) -> None:
    """Explain that a matching command is denied before approval."""
    print("Execution Blocked")
    print(f"Rule:\n{rule}")
    print(f"Command:\n{command}")


def _maintenance_allowed(manager: MaintenanceManager, profile_name: str) -> bool:
    """Check the active local-time window and explain a denial."""
    now = datetime.now().astimezone()
    if manager.is_allowed(profile_name, now):
        return True
    print(f"Current Profile:\n{profile_name}")
    print(f"Current Time:\n{now.strftime('%H:%M %Z').strip()}")
    print("Execution Blocked")
    print("Reason:\nOutside approved maintenance window")
    return False


def _handle_maintenance_command(raw_command: str, manager: MaintenanceManager | None) -> bool:
    """Handle local maintenance configuration commands."""
    stripped = raw_command.strip()
    if not stripped.casefold().startswith("maintenance"):
        return False
    if manager is None:
        print("Maintenance settings are unavailable.")
        return True
    try:
        parts = shlex.split(stripped)
        if len(parts) == 1:
            print(f"Maintenance Windows: {'ENABLED' if manager.enabled else 'DISABLED'}")
            windows = manager.list_windows()
            if windows:
                for window in windows:
                    print(f"- {window.name}: {','.join(window.days)} {window.start}-{window.end}")
            else:
                print("No windows configured.")
            return True
        action = parts[1].casefold()
        if action in ("enable", "disable") and len(parts) == 2:
            manager.set_enabled(action == "enable")
            print(f"Maintenance windows {'enabled' if action == 'enable' else 'disabled'}.")
        elif action == "add" and len(parts) == 6:
            window = MaintenanceWindow(parts[2], parts[3].split(","), parts[4], parts[5])
            added = manager.add_window(window)
            print("Maintenance window added." if added else "Maintenance window already exists.")
        elif action == "remove" and len(parts) == 3:
            removed = manager.remove_window(parts[2])
            print("Maintenance window removed." if removed else "Maintenance window not found.")
        else:
            print("Usage: maintenance [enable|disable|add PROFILE DAYS START END|remove PROFILE]")
    except (ValueError, TypeError, MaintenanceError) as exc:
        print(f"Unable to update maintenance settings:\n{exc}")
    return True


def _parse_target(raw_prompt: str) -> tuple[str | None, str, str]:
    """Parse local/remote target prefixes and return host, intent, cache key."""
    stripped = raw_prompt.strip()
    folded = stripped.casefold()
    if folded.startswith("remote>"):
        target = stripped[len("remote>"):].strip()
        fields = target.split(maxsplit=1)
        if len(fields) != 2:
            raise ValueError("Remote syntax is: remote> HOST natural-language request")
        host, intent = fields
        return host, intent, f"remote:{host} {intent}"
    if folded.startswith("local>"):
        intent = stripped[len("local>"):].strip()
        return None, intent, intent
    return None, stripped, stripped


def _authorize_command(
    engine: RbacEngine,
    user: UserContext,
    risk_level: RiskLevel,
) -> AuthorizationDecision:
    """Display the role decision and obtain any required explicit override."""
    decision = engine.authorize(user, risk_level)
    print(f"User:\n{user.username}")
    print(f"Role:\n{user.role.name}")
    print(f"Authorization:\n{decision.name}")
    if decision is AuthorizationDecision.REQUIRE_OVERRIDE and not _confirm_role_override():
        print("Role override cancelled.")
        return AuthorizationDecision.DENY
    return decision


def _get_reputation(
    engine: ReputationEngine | None,
    command: str,
) -> CommandReputation | None:
    """Return local reputation, treating unavailable history as unknown."""
    if engine is None:
        return None
    try:
        return engine.get_reputation(command)
    except FeedbackStoreError as exc:
        print(f"Reputation unavailable:\n{exc}")
        return None


def _display_command_policy(
    command: str,
    risk_level: RiskLevel,
    risk_reasons: list[str],
    reputation: CommandReputation | None,
    policy: PolicyResult,
    target_host: str | None = None,
    profile: PolicyProfile | None = None,
) -> None:
    """Display the assessed command, its history, and the policy outcome."""
    print("Generated Command:")
    print(command)
    if target_host is not None:
        print(f"\nExecution Target:\nRemote host: {target_host}")
    if profile is not None:
        print(f"\nProfile:\n{profile.name}")
    print(f"\nRisk Level:\n{risk_level.name}")
    print("Reasons:")
    for reason in risk_reasons or ["No known risky patterns detected."]:
        print(f"- {reason}")
    print(f"\nReputation:\n{reputation.score:g}" if reputation else "\nReputation:\nUnknown")
    if reputation:
        print(f"Successes:\n{reputation.success_count}")
        print(f"Failures:\n{reputation.failure_count}")
        print(f"Dangerous:\n{reputation.dangerous_count}")
    print(f"\nPolicy:\n{policy.decision.name.replace('_', ' ')}")
    print(f"Decision:\n{policy.decision.name.replace('_', ' ')}")
    print("Policy Reasons:")
    for reason in policy.reasons or ["No policy concerns detected."]:
        print(f"- {reason}")


def _append_audit_record(
    store: AuditStore | None,
    intent: str,
    command: str,
    risk_level: str,
    return_code: int,
    success: bool,
    host: str | None = None,
) -> AuditStore | None:
    """Append one approved execution attempt, reporting storage failures."""
    try:
        if store is None:
            store = AuditStore()
        store.append(
            AuditRecord(
                timestamp=utc_timestamp(),
                intent=intent,
                command=command,
                risk_level=risk_level,
                approval_result="approved",
                return_code=return_code,
                success=success,
                host=host,
            )
        )
    except AuditStoreError as exc:
        print(f"Unable to write execution audit record:\n{exc}")
    return store


def main() -> None:
    """Run the prompt, generate, approve, and execute loop."""
    provider = None
    approval_manager = ApprovalManager()
    execution_manager = ExecutionManager()
    risk_engine = RiskEngine()
    rbac_engine = RbacEngine()
    user_context = UserContext(username="local", role=Role.ADMIN)
    policy_engine = PolicyEngine()
    try:
        reputation_engine = ReputationEngine()
    except FeedbackStoreError as exc:
        reputation_engine = None
        print(f"Reputation unavailable:\n{exc}")
    audit_store = None
    try:
        command_cache = CommandCache()
    except CacheError as exc:
        command_cache = None
        print(f"Command cache unavailable:\n{exc}")
    try:
        host_inventory = HostInventory()
    except InventoryError as exc:
        host_inventory = None
        print(f"Host inventory unavailable:\n{exc}")
    try:
        profile_manager = ProfileManager()
        current_profile = profile_manager.get_default_profile()
    except ProfileStoreError as exc:
        profile_manager = None
        current_profile = None
        print(f"Policy profiles unavailable:\n{exc}")
    try:
        blocklist = CommandBlocklist()
    except BlocklistError as exc:
        blocklist = None
        print(f"Command blocklist unavailable:\n{exc}")
    try:
        maintenance_manager = MaintenanceManager()
    except MaintenanceError as exc:
        maintenance_manager = None
        print(f"Maintenance settings unavailable:\n{exc}")

    print("-" * 36)
    print("GOYATHLAY")
    print("-" * 36)
    if current_profile is not None:
        print(f"Current Profile: {current_profile.name}")
    print("Type 'exit' or 'quit' to leave.")

    while True:
        try:
            raw_prompt = input("goyathlay> ").strip()
        except KeyboardInterrupt:
            print("\nExiting Goyathlay.")
            return

        if raw_prompt.casefold() in ("exit", "quit"):
            return
        if not raw_prompt:
            continue
        if _handle_blocklist_command(raw_prompt, blocklist):
            continue
        if _handle_maintenance_command(raw_prompt, maintenance_manager):
            continue
        command_parts = raw_prompt.split(maxsplit=1)
        command_name = command_parts[0].casefold()
        if command_name == "profiles" and len(command_parts) == 1:
            if profile_manager is None:
                print("Policy profiles are unavailable.")
            else:
                print("Available Profiles:")
                for configured in profile_manager.list_profiles():
                    print(f"- {configured.name}")
            continue
        if command_name == "profile":
            if profile_manager is None:
                print("Policy profiles are unavailable.")
            elif len(command_parts) != 2:
                print("Usage: profile NAME")
            else:
                try:
                    profile_manager.set_default_profile(command_parts[1])
                    current_profile = profile_manager.load_profile(command_parts[1])
                    print(f"Current Profile: {current_profile.name}")
                except ProfileNotFoundError as exc:
                    print(exc)
                except ProfileStoreError as exc:
                    print(f"Unable to switch profile:\n{exc}")
            continue
        if current_profile is None:
            print("Command blocked because no policy profile is available.")
            continue
        if maintenance_manager is None:
            print("Command blocked because maintenance settings are unavailable.")
            continue
        if not _maintenance_allowed(maintenance_manager, current_profile.name):
            continue
        if blocklist is None:
            print("Command blocked because the blocklist is unavailable.")
            continue
        try:
            target_name, prompt, cache_intent = _parse_target(raw_prompt)
        except ValueError as exc:
            print(exc)
            continue
        if not prompt:
            continue
        if prompt.casefold() in ("exit", "quit"):
            return

        target_records = []
        if target_name is not None:
            if host_inventory is None:
                print("Remote target unavailable because the host inventory could not be loaded.")
                continue
            try:
                targets = host_inventory.resolve_target(target_name)
            except InventoryError as exc:
                print(f"Unable to resolve remote target:\n{exc}")
                continue
            print("Targets:")
            for record in targets:
                print(f"- {record.name}")
            target_records = targets
            if not target_records:
                print("The selected target has no hosts.")
                continue
        target_record = target_records[0] if len(target_records) == 1 else None
        target_host = target_record.hostname if target_record is not None else None
        target_display = (
            ", ".join(
                f"{record.name} ({record.hostname}:{record.port})"
                for record in target_records
            )
            if target_records
            else None
        )

        try:
            cached = command_cache.get_verified(cache_intent) if command_cache is not None else None
            use_cached = cached is not None and _confirm_cached_command(cache_intent, cached.command)
            if use_cached:
                command = clean_command(cached.command)
            else:
                if provider is None:
                    provider = _create_provider()
                generated_command = provider.generate_command(prompt)
                command = clean_command(generated_command)
        except KeyboardInterrupt:
            print("\nExiting Goyathlay.")
            return
        except Exception as exc:
            print(f"Unable to generate command:\n{exc}")
            continue

        blocked_rule = blocklist.blocked_by(command)
        if blocked_rule is not None:
            _display_blocked_command(blocked_rule, command)
            continue
        assessment = risk_engine.assess(command)

        reputation = _get_reputation(reputation_engine, command)
        authorization = _authorize_command(rbac_engine, user_context, assessment.level)
        if authorization is AuthorizationDecision.DENY:
            print("Execution blocked.")
            continue
        policy = policy_engine.evaluate(
            assessment.level,
            reputation.score if reputation is not None else None,
            current_profile,
        )
        _display_command_policy(
            command,
            assessment.level,
            assessment.reasons,
            reputation,
            policy,
            target_display,
            current_profile,
        )
        if policy.decision is PolicyDecision.DENY:
            print("Execution blocked.")
            continue

        try:
            if assessment.level is RiskLevel.HIGH and not _confirm_high_risk():
                print("High-risk command cancelled.")
                continue
            if policy.decision is PolicyDecision.REQUIRE_EXTRA_CONFIRMATION and not _confirm_policy_override():
                print("Policy override cancelled.")
                continue

            approved, approved_command = approval_manager.review(command, display_command=False)
        except KeyboardInterrupt:
            print("\nExiting Goyathlay.")
            return
        if not approved or approved_command is None:
            print("Command cancelled.")
            continue

        if approved_command != command:
            blocked_rule = blocklist.blocked_by(approved_command)
            if blocked_rule is not None:
                _display_blocked_command(blocked_rule, approved_command)
                continue
            final_assessment = risk_engine.assess(approved_command)
            final_reputation = _get_reputation(reputation_engine, approved_command)
            final_authorization = _authorize_command(
                rbac_engine, user_context, final_assessment.level
            )
            if final_authorization is AuthorizationDecision.DENY:
                print("Execution blocked.")
                continue
            final_policy = policy_engine.evaluate(
                final_assessment.level,
                final_reputation.score if final_reputation is not None else None,
                current_profile,
            )
            _display_command_policy(
                approved_command,
                final_assessment.level,
                final_assessment.reasons,
                final_reputation,
                final_policy,
                target_display,
                current_profile,
            )
            if final_policy.decision is PolicyDecision.DENY:
                print("Execution blocked.")
                continue
            if final_assessment.level is RiskLevel.HIGH and not _confirm_high_risk():
                print("High-risk command cancelled.")
                continue
            if final_policy.decision is PolicyDecision.REQUIRE_EXTRA_CONFIRMATION and not _confirm_policy_override():
                print("Policy override cancelled.")
                continue
            reputation = final_reputation
            policy = final_policy
            assessment = final_assessment

        # Approval and TOFU prompts can consume time; recheck at the execution boundary.
        if not _maintenance_allowed(maintenance_manager, current_profile.name):
            continue

        ssh_client = None
        fanout_results: list[HostExecutionResult] | None = None
        try:
            if target_host is None:
                if target_records:
                    fanout_results = FanoutExecutor().execute(target_records, approved_command)
                else:
                    result = execution_manager.execute(approved_command)
                    return_code = result.returncode
            else:
                ssh_client = SSHConnector().connect(
                    target_host,
                    username=target_record.username,
                    port=target_record.port,
                )
                remote_result = SSHExecutor().execute(ssh_client, approved_command)
                return_code = remote_result.exit_code
                result = remote_result
        except KeyboardInterrupt:
            print("\nExiting Goyathlay.")
            return
        except SSHConnectionError as exc:
            print(f"Remote connection failed:\n{exc}")
            continue
        except SSHExecutionError as exc:
            audit_store = _append_audit_record(
                audit_store,
                cache_intent,
                approved_command,
                assessment.level.name,
                -1,
                False,
            )
            print(f"Remote execution failed:\n{exc}")
            continue
        except ExecutionError as exc:
            audit_store = _append_audit_record(
                audit_store,
                cache_intent,
                approved_command,
                assessment.level.name,
                exc.return_code if exc.return_code is not None else -1,
                False,
            )
            print(f"Execution failed:\n{exc}")
            continue
        finally:
            if ssh_client is not None:
                ssh_client.close()

        if fanout_results is not None:
            successes = sum(result.success for result in fanout_results)
            for host_result in fanout_results:
                print(f"Host: {host_result.host}")
                print(f"Success: {host_result.success}")
                if host_result.exit_code != 0:
                    print(f"Exit Code: {host_result.exit_code}")
                if host_result.stdout:
                    print("STDOUT:")
                    print(host_result.stdout, end="" if host_result.stdout.endswith("\n") else "\n")
                if host_result.stderr:
                    print("STDERR:")
                    print(host_result.stderr, end="" if host_result.stderr.endswith("\n") else "\n")
                audit_store = _append_audit_record(
                    audit_store,
                    cache_intent,
                    approved_command,
                    assessment.level.name,
                    host_result.exit_code,
                    host_result.success,
                    host=host_result.host,
                )
            print("Summary:")
            print(f"{len(fanout_results)} Hosts")
            print(f"{successes} Success")
            print(f"{len(fanout_results) - successes} Failure")
        else:
            audit_store = _append_audit_record(
                audit_store,
                cache_intent,
                approved_command,
                assessment.level.name,
                return_code,
                return_code == 0,
                host=target_record.name if target_record is not None else None,
            )

            print(f"Return Code: {return_code}")
            print("STDOUT:")
            if result.stdout:
                print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
            if result.stderr:
                print("STDERR:")
                print(result.stderr, end="" if result.stderr.endswith("\n") else "\n")

        try:
            feedback_result = FeedbackManager().review(cache_intent, approved_command)
        except KeyboardInterrupt:
            print("\nExiting Goyathlay.")
            return
        except FeedbackStoreError as exc:
            print(f"Unable to store command feedback:\n{exc}")
            continue

        if command_cache is None or feedback_result is FeedbackResult.SKIPPED:
            continue
        if (
            fanout_results is not None
            and not all(host_result.success for host_result in fanout_results)
            and feedback_result is FeedbackResult.SUCCESS
        ):
            print("Command was not cached as verified because at least one host failed.")
            continue

        try:
            if feedback_result is FeedbackResult.SUCCESS:
                command_cache.record_success(cache_intent, approved_command)
            elif feedback_result is FeedbackResult.FAILURE:
                command_cache.record_failure(cache_intent, approved_command)
            elif feedback_result is FeedbackResult.DANGEROUS:
                command_cache.record_dangerous(cache_intent, approved_command)
        except CacheError as exc:
            print(f"Unable to update command cache:\n{exc}")


if __name__ == "__main__":
    main()
