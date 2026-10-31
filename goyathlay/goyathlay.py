#!/usr/bin/env python3
"""Interactive, local-first Goyathlay command line application."""

import getpass

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
) -> None:
    """Display the assessed command, its history, and the policy outcome."""
    print("Generated Command:")
    print(command)
    if target_host is not None:
        print(f"\nExecution Target:\nRemote host: {target_host}")
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

    print("-" * 36)
    print("GOYATHLAY")
    print("-" * 36)
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
        try:
            target_host, prompt, cache_intent = _parse_target(raw_prompt)
        except ValueError as exc:
            print(exc)
            continue
        if not prompt:
            continue
        if prompt.casefold() in ("exit", "quit"):
            return

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
            assessment = risk_engine.assess(command)
        except KeyboardInterrupt:
            print("\nExiting Goyathlay.")
            return
        except Exception as exc:
            print(f"Unable to generate command:\n{exc}")
            continue

        reputation = _get_reputation(reputation_engine, command)
        authorization = _authorize_command(rbac_engine, user_context, assessment.level)
        if authorization is AuthorizationDecision.DENY:
            print("Execution blocked.")
            continue
        policy = policy_engine.evaluate(
            assessment.level,
            reputation.score if reputation is not None else None,
        )
        _display_command_policy(
            command, assessment.level, assessment.reasons, reputation, policy, target_host
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

        final_assessment = risk_engine.assess(approved_command)
        if approved_command != command:
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
            )
            _display_command_policy(
                approved_command,
                final_assessment.level,
                final_assessment.reasons,
                final_reputation,
                final_policy,
                target_host,
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

        ssh_client = None
        try:
            if target_host is None:
                result = execution_manager.execute(approved_command)
                return_code = result.returncode
            else:
                ssh_client = SSHConnector().connect(
                    target_host,
                    username=getpass.getuser(),
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

        audit_store = _append_audit_record(
            audit_store,
            cache_intent,
            approved_command,
            assessment.level.name,
            return_code,
            return_code == 0,
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
