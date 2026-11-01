#!/usr/bin/env python3
"""Interactive, local-first Goyathlay command line application."""

import shlex
from dataclasses import replace
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
    from .db import (
        DatabaseConnectionError,
        DatabaseProfileError,
        DatabaseProfileNotFoundError,
        DatabaseQuery,
        PostgresConnectionManager,
        PostgresExecutionError,
        PostgresExecutor,
        PostgresInterpreter,
    )
    from .db.sqlite import SqliteInterpreter
    from .db.sqlite_executor import SqliteExecutionError, SqliteExecutor
    from .db.sqlite_profiles import (
        SqliteProfile,
        SqliteProfileError,
        SqliteProfileManager,
        SqliteProfileNotFoundError,
    )
    from .db.mssql import MssqlInterpreter
    from .db.mssql_executor import MssqlExecutionError, MssqlExecutor
    from .db.mssql_profiles import MssqlProfileError, MssqlProfileManager, MssqlProfileNotFoundError
    from .planning import ExecutionPlan, render_plan
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
    from db import (
        DatabaseConnectionError,
        DatabaseProfileError,
        DatabaseProfileNotFoundError,
        DatabaseQuery,
        PostgresConnectionManager,
        PostgresExecutionError,
        PostgresExecutor,
        PostgresInterpreter,
    )
    from db.sqlite import SqliteInterpreter
    from db.sqlite_executor import SqliteExecutionError, SqliteExecutor
    from db.sqlite_profiles import (
        SqliteProfile,
        SqliteProfileError,
        SqliteProfileManager,
        SqliteProfileNotFoundError,
    )
    from db.mssql import MssqlInterpreter
    from db.mssql_executor import MssqlExecutionError, MssqlExecutor
    from db.mssql_profiles import MssqlProfileError, MssqlProfileManager, MssqlProfileNotFoundError
    from planning import ExecutionPlan, render_plan


def _create_provider():
    """Load the Ollama provider only when a prompt needs generation."""
    if __package__:
        from .providers.ollama_provider import OllamaProvider
    else:
        from providers.ollama_provider import OllamaProvider
    return OllamaProvider()


def _check_ollama_installation() -> str | None:
    """Return package-install guidance for startup when the SDK is missing."""
    if __package__:
        from .providers.ollama_provider import ollama_package_error
    else:
        from providers.ollama_provider import ollama_package_error
    return ollama_package_error()


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


def _most_restrictive_policy(policies: list[tuple[str | None, PolicyProfile, PolicyResult]]) -> PolicyResult:
    """Combine host decisions conservatively: any denial blocks the operation."""
    rank = {
        PolicyDecision.ALLOW: 0,
        PolicyDecision.REQUIRE_EXTRA_CONFIRMATION: 1,
        PolicyDecision.DENY: 2,
    }
    decision = max((result.decision for _host, _profile, result in policies), key=rank.__getitem__)
    reasons = []
    for host, profile, result in policies:
        if result.decision is not PolicyDecision.ALLOW:
            label = f"{host} ({profile.name})" if host else profile.name
            reasons.extend(f"{label}: {reason}" for reason in result.reasons)
    return PolicyResult(decision, reasons)


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


def _handle_db_profile_command(raw_command: str, manager: PostgresConnectionManager | None) -> bool:
    """Handle `db profiles` and persisted default profile selection."""
    parts = raw_command.strip().split()
    if not parts or parts[0].casefold() != "db":
        return False
    if len(parts) == 2 and parts[1].casefold() == "profiles":
        if manager is None:
            print("Database profiles are unavailable.")
            return True
        print("Database Profiles:")
        profiles = manager.list_profiles()
        default_name = manager.profile_store.default_name
        for profile in profiles:
            marker = " (default)" if profile.name == default_name else ""
            print(f"- {profile.name}: {profile.username}@{profile.host}:{profile.port}/{profile.database}{marker}")
        if not profiles:
            print("No database profiles configured.")
        return True
    if len(parts) == 3 and parts[1].casefold() == "profile":
        if manager is None:
            print("Database profiles are unavailable.")
            return True
        try:
            manager.set_default_profile(parts[2])
            print(f"Current Database Profile: {manager.load_profile().name}")
        except DatabaseProfileNotFoundError as exc:
            print(exc)
        except DatabaseProfileError as exc:
            print(f"Unable to select database profile:\n{exc}")
        return True
    return False


def _handle_sqlite_profile_command(raw_command: str, manager: SqliteProfileManager | None) -> bool:
    """Handle SQLite profile listing and default selection commands."""
    parts = raw_command.strip().split()
    if not parts or parts[0].casefold() != "sqlite":
        return False
    if len(parts) == 2 and parts[1].casefold() == "profiles":
        if manager is None:
            print("SQLite profiles are unavailable.")
            return True
        print("SQLite Profiles:")
        default_name = manager.default_name
        profiles = manager.list_profiles()
        for profile in profiles:
            marker = " (default)" if profile.name == default_name else ""
            print(f"- {profile.name}: {profile.database}{marker}")
        if not profiles:
            print("No SQLite profiles configured.")
        return True
    if len(parts) == 3 and parts[1].casefold() == "profile":
        if manager is None:
            print("SQLite profiles are unavailable.")
            return True
        try:
            manager.set_default_profile(parts[2])
            print(f"Current SQLite Profile: {manager.get_default_profile().name}")
        except SqliteProfileNotFoundError as exc:
            print(exc)
        except SqliteProfileError as exc:
            print(f"Unable to select SQLite profile:\n{exc}")
        return True
    return False


def _handle_mssql_profile_command(raw_command: str, manager: MssqlProfileManager | None) -> bool:
    """Handle SQL Server profile listing and selection."""
    parts = raw_command.strip().split()
    if not parts or parts[0].casefold() != "mssql":
        return False
    if len(parts) == 2 and parts[1].casefold() == "profiles":
        if manager is None:
            print("MSSQL profiles are unavailable.")
            return True
        print("MSSQL Profiles:")
        for profile in manager.list_profiles():
            marker = " (default)" if profile.name == manager.default_name else ""
            print(f"- {profile.name}: {profile.username}@{profile.server}:{profile.port}/{profile.database}{marker}")
        if not manager.list_profiles():
            print("No MSSQL profiles configured.")
        return True
    if len(parts) == 3 and parts[1].casefold() == "profile":
        if manager is None:
            print("MSSQL profiles are unavailable.")
            return True
        try:
            manager.set_default_profile(parts[2])
            print(f"Current MSSQL Profile: {manager.get_default_profile().name}")
        except MssqlProfileNotFoundError as exc:
            print(exc)
        except MssqlProfileError as exc:
            print(f"Unable to select MSSQL profile:\n{exc}")
        return True
    return False


def _parse_database_prompt(raw_prompt: str) -> tuple[str | None, str] | None:
    """Return the optional profile and intent from a `db>` prompt."""
    if not raw_prompt.lstrip().casefold().startswith("db>"):
        return None
    body = raw_prompt.lstrip()[3:].strip()
    if not body:
        return (None, "")
    first, separator, remainder = body.partition(" ")
    if first.casefold() == "show":
        return (None, body)
    return (first, remainder.strip() if separator else "")


def _parse_sqlite_prompt(raw_prompt: str) -> tuple[str | None, str] | None:
    """Return an optional profile name and intent from a `sqlite>` prompt."""
    stripped = raw_prompt.lstrip()
    if not stripped.casefold().startswith("sqlite>"):
        return None
    body = stripped[len("sqlite>"):].strip()
    if not body:
        return (None, "")
    first, separator, remainder = body.partition(" ")
    if first.casefold() in {"show", "count"}:
        return (None, body)
    return (first, remainder.strip() if separator else "")


def _parse_mssql_prompt(raw_prompt: str) -> tuple[str | None, str] | None:
    """Return an optional profile name and intent from an `mssql>` prompt."""
    stripped = raw_prompt.lstrip()
    if not stripped.casefold().startswith("mssql>"):
        return None
    body = stripped[len("mssql>"):].strip()
    if not body:
        return (None, "")
    first, separator, remainder = body.partition(" ")
    if first.casefold() == "show":
        return (None, body)
    return (first, remainder.strip() if separator else "")


def _append_database_audit(
    store: AuditStore | None,
    *,
    intent: str,
    query: str,
    profile: str,
    host: str | None,
    row_count: int | None,
    success: bool,
    engine: str = "postgres",
    database_path: str | None = None,
) -> AuditStore | None:
    """Append one approved database query execution outcome."""
    try:
        if store is None:
            store = AuditStore()
        store.append(
            AuditRecord(
                timestamp=utc_timestamp(),
                intent=intent,
                command=query,
                risk_level="LOW",
                approval_result="approved",
                return_code=0 if success else -1,
                success=success,
                host=host,
                database_profile=profile,
                row_count=row_count,
                database_engine=engine,
                database_path=database_path,
            )
        )
    except AuditStoreError as exc:
        print(f"Unable to write database audit record:\n{exc}")
    return store


def _handle_database_prompt(
    raw_prompt: str,
    manager: PostgresConnectionManager | None,
    approval_manager: ApprovalManager,
    risk_engine: RiskEngine,
    audit_store: AuditStore | None,
) -> tuple[bool, AuditStore | None]:
    """Translate, validate, approve, execute, audit, and collect query feedback."""
    parsed = _parse_database_prompt(raw_prompt)
    if parsed is None:
        return False, audit_store
    if manager is None:
        print("Database execution is unavailable because profiles could not be loaded.")
        return True, audit_store
    profile_name, intent = parsed
    if not intent:
        print("Usage: db> [PROFILE] show tables")
        return True, audit_store
    try:
        profile = manager.load_profile(profile_name)
        interpreter = PostgresInterpreter()
        query = interpreter.translate(intent)
    except (DatabaseProfileError, ValueError) as exc:
        print(f"Unable to prepare PostgreSQL query:\n{exc}")
        return True, audit_store

    validation = interpreter.validate(query.sql)
    if not validation.allowed:
        print(f"SQL validation blocked execution:\n{validation.reason}")
        return True, audit_store
    assessment = risk_engine.assess(query.sql)
    print("Database: PostgreSQL")
    print(f"Profile: {profile.name}")
    print(f"Host: {profile.host}")
    print("Generated SQL:")
    print(query.sql)
    print(f"Risk: {assessment.level.name}")
    try:
        approved, approved_sql = approval_manager.review(query.sql, display_command=False)
    except KeyboardInterrupt:
        print("\nExiting Goyathlay.")
        return True, audit_store
    if not approved or approved_sql is None:
        print("Database query cancelled.")
        return True, audit_store

    final_validation = interpreter.validate(approved_sql)
    if not final_validation.allowed:
        print(f"SQL validation blocked execution:\n{final_validation.reason}")
        return True, audit_store
    final_query = replace(query, sql=approved_sql)
    try:
        result = PostgresExecutor(manager).execute(final_query, profile)
    except (DatabaseConnectionError, PostgresExecutionError) as exc:
        audit_store = _append_database_audit(
            audit_store,
            intent=intent,
            query=approved_sql,
            profile=profile.name,
            host=profile.host,
            row_count=None,
            success=False,
        )
        print(f"PostgreSQL execution failed:\n{exc}")
        return True, audit_store

    print(f"Columns: {', '.join(result.columns)}")
    print(f"Rows: {result.row_count}")
    for row in result.rows:
        print("\t".join("NULL" if value is None else str(value) for value in row))
    audit_store = _append_database_audit(
        audit_store,
        intent=intent,
        query=approved_sql,
        profile=profile.name,
        host=profile.host,
        row_count=result.row_count,
        success=True,
    )
    try:
        FeedbackManager().review(intent, approved_sql)
    except KeyboardInterrupt:
        print("\nExiting Goyathlay.")
    except FeedbackStoreError as exc:
        print(f"Unable to store database feedback:\n{exc}")
    return True, audit_store


def _handle_sqlite_prompt(
    raw_prompt: str,
    manager: SqliteProfileManager | None,
    approval_manager: ApprovalManager,
    risk_engine: RiskEngine,
    audit_store: AuditStore | None,
) -> tuple[bool, AuditStore | None]:
    """Translate, approve, execute, audit, and collect feedback for SQLite."""
    parsed = _parse_sqlite_prompt(raw_prompt)
    if parsed is None:
        return False, audit_store
    if manager is None:
        print("SQLite execution is unavailable because profiles could not be loaded.")
        return True, audit_store
    profile_name, intent = parsed
    if not intent:
        print("Usage: sqlite> [PROFILE] show tables")
        return True, audit_store
    try:
        profile = manager.load_profile(profile_name) if profile_name else manager.get_default_profile()
        interpreter = SqliteInterpreter()
        query = interpreter.translate(intent)
    except (SqliteProfileError, ValueError) as exc:
        print(f"Unable to prepare SQLite query:\n{exc}")
        return True, audit_store

    validation = interpreter.validate(query.sql)
    if not validation.allowed:
        print(f"SQL validation blocked execution:\n{validation.reason}")
        return True, audit_store
    assessment = risk_engine.assess(query.sql)
    print(f"Profile:\n{profile.name}")
    print(f"Database:\n{profile.database}")
    print("Generated SQL:")
    print(query.sql)
    print(f"Risk:\n{assessment.level.name}")
    try:
        approved, approved_sql = approval_manager.review(query.sql, display_command=False)
    except KeyboardInterrupt:
        print("\nExiting Goyathlay.")
        return True, audit_store
    if not approved or approved_sql is None:
        print("SQLite query cancelled.")
        return True, audit_store

    final_validation = interpreter.validate(approved_sql)
    if not final_validation.allowed:
        print(f"SQL validation blocked execution:\n{final_validation.reason}")
        return True, audit_store
    try:
        result = SqliteExecutor().execute(profile, approved_sql)
    except SqliteExecutionError as exc:
        audit_store = _append_database_audit(
            audit_store,
            intent=intent,
            query=approved_sql,
            profile=profile.name,
            host=None,
            row_count=None,
            success=False,
            engine="sqlite",
            database_path=profile.database,
        )
        print(f"SQLite execution failed:\n{exc}")
        return True, audit_store

    print(f"Columns: {', '.join(result.columns)}")
    print(f"Rows: {result.row_count}")
    for row in result.rows:
        print("\t".join("NULL" if value is None else str(value) for value in row))
    audit_store = _append_database_audit(
        audit_store,
        intent=intent,
        query=approved_sql,
        profile=profile.name,
        host=None,
        row_count=result.row_count,
        success=True,
        engine="sqlite",
        database_path=profile.database,
    )
    try:
        FeedbackManager().review(intent, approved_sql)
    except KeyboardInterrupt:
        print("\nExiting Goyathlay.")
    except FeedbackStoreError as exc:
        print(f"Unable to store SQLite feedback:\n{exc}")
    return True, audit_store


def _handle_mssql_prompt(
    raw_prompt: str,
    manager: MssqlProfileManager | None,
    approval_manager: ApprovalManager,
    risk_engine: RiskEngine,
    audit_store: AuditStore | None,
) -> tuple[bool, AuditStore | None]:
    """Translate, validate, approve, execute, audit, and collect SQL Server feedback."""
    parsed = _parse_mssql_prompt(raw_prompt)
    if parsed is None:
        return False, audit_store
    if manager is None:
        print("MSSQL execution is unavailable because profiles could not be loaded.")
        return True, audit_store
    profile_name, intent = parsed
    if not intent:
        print("Usage: mssql> [PROFILE] show tables")
        return True, audit_store
    try:
        profile = manager.load_profile(profile_name) if profile_name else manager.get_default_profile()
        interpreter = MssqlInterpreter()
        query = interpreter.translate(intent)
    except (MssqlProfileError, ValueError) as exc:
        print(f"Unable to prepare MSSQL query:\n{exc}")
        return True, audit_store

    validation = interpreter.validate(query.sql)
    if not validation.allowed:
        print(f"SQL validation blocked execution:\n{validation.reason}")
        return True, audit_store
    assessment = risk_engine.assess(query.sql)
    print("Database:\nMicrosoft SQL Server")
    print(f"Profile:\n{profile.name}")
    print(f"Host:\n{profile.server}:{profile.port}")
    print("Generated SQL:")
    print(query.sql)
    print(f"Risk:\n{assessment.level.name}")
    try:
        approved, approved_sql = approval_manager.review(query.sql, display_command=False)
    except KeyboardInterrupt:
        print("\nExiting Goyathlay.")
        return True, audit_store
    if not approved or approved_sql is None:
        print("MSSQL query cancelled.")
        return True, audit_store

    final_validation = interpreter.validate(approved_sql)
    if not final_validation.allowed:
        print(f"SQL validation blocked execution:\n{final_validation.reason}")
        return True, audit_store
    try:
        result = MssqlExecutor(manager).execute(profile, approved_sql)
    except MssqlExecutionError as exc:
        audit_store = _append_database_audit(
            audit_store, intent=intent, query=approved_sql, profile=profile.name,
            host=profile.server, row_count=None, success=False, engine="mssql",
            database_path=profile.database,
        )
        print(f"MSSQL execution failed:\n{exc}")
        return True, audit_store

    print(f"Columns: {', '.join(result.columns)}")
    print(f"Rows: {result.row_count}")
    for row in result.rows:
        print("\t".join("NULL" if value is None else str(value) for value in row))
    audit_store = _append_database_audit(
        audit_store, intent=intent, query=approved_sql, profile=profile.name,
        host=profile.server, row_count=result.row_count, success=True, engine="mssql",
        database_path=profile.database,
    )
    try:
        FeedbackManager().review(intent, approved_sql)
    except KeyboardInterrupt:
        print("\nExiting Goyathlay.")
    except FeedbackStoreError as exc:
        print(f"Unable to store database feedback:\n{exc}")
    return True, audit_store


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
    try:
        ollama_error = _check_ollama_installation()
    except ImportError:
        ollama_error = "Ollama Python package is not installed.\nRun:\npip install ollama"
    if ollama_error:
        print(ollama_error)
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
    try:
        database_manager = PostgresConnectionManager()
    except DatabaseProfileError as exc:
        database_manager = None
        print(f"Database profiles unavailable:\n{exc}")
    try:
        sqlite_profile_manager = SqliteProfileManager()
    except SqliteProfileError as exc:
        sqlite_profile_manager = None
        print(f"SQLite profiles unavailable:\n{exc}")
    try:
        mssql_profile_manager = MssqlProfileManager()
    except MssqlProfileError as exc:
        mssql_profile_manager = None
        print(f"MSSQL profiles unavailable:\n{exc}")

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
        if raw_prompt.casefold().startswith("dryrun>"):
            dry_intent = raw_prompt[len("dryrun>"):].strip()
            if not dry_intent:
                print("Usage: dryrun> PROMPT")
                continue
            dry_targets: tuple[str, ...] = ()
            try:
                target_name, generation_prompt, _ = _parse_target(dry_intent)
                if target_name is not None and host_inventory is not None:
                    dry_targets = tuple(record.name for record in host_inventory.resolve_target(target_name))
                elif target_name is not None:
                    print("Remote target unavailable because the host inventory could not be loaded.")
                    continue
                if provider is None:
                    provider = _create_provider()
                generated = clean_command(provider.generate_command(generation_prompt))
                risk = risk_engine.assess(generated)
                reputation = _get_reputation(reputation_engine, generated)
                policy = policy_engine.evaluate(
                    risk.level, reputation.score if reputation is not None else None, current_profile
                )
                plan = ExecutionPlan(
                    intent=dry_intent,
                    command=generated,
                    risk=risk.level.name,
                    reputation=reputation.score if reputation is not None else None,
                    policy=policy.decision.name,
                    targets=dry_targets,
                )
                print("DRY RUN — no command was approved or executed.")
                print(render_plan(plan))
            except (KeyboardInterrupt, EOFError):
                print("\nExiting Goyathlay.")
                return
            except Exception as exc:
                print(f"Unable to create dry-run plan:\n{exc}")
            continue
        if _handle_blocklist_command(raw_prompt, blocklist):
            continue
        if _handle_maintenance_command(raw_prompt, maintenance_manager):
            continue
        if _handle_db_profile_command(raw_prompt, database_manager):
            continue
        if _handle_sqlite_profile_command(raw_prompt, sqlite_profile_manager):
            continue
        if _handle_mssql_profile_command(raw_prompt, mssql_profile_manager):
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
        if command_name == "host-profile":
            if profile_manager is None:
                print("Policy profiles are unavailable.")
            elif len(command_parts) != 2:
                print('Usage: host-profile HOST PROFILE | host-profile HOST default')
            else:
                try:
                    host_name, profile_name = command_parts[1].split(maxsplit=1)
                    override = None if profile_name.casefold() == "default" else profile_name
                    profile_manager.set_host_profile(host_name, override)
                    effective = profile_manager.get_profile_for_host(host_name)
                    print(f"Policy Profile for {host_name}: {effective.name}")
                except ValueError:
                    print('Usage: host-profile HOST PROFILE | host-profile HOST default')
                except (ProfileNotFoundError, ProfileStoreError) as exc:
                    print(f"Unable to set host profile:\n{exc}")
            continue
        if current_profile is None:
            print("Command blocked because no policy profile is available.")
            continue
        if maintenance_manager is None:
            print("Command blocked because maintenance settings are unavailable.")
            continue
        if not _maintenance_allowed(maintenance_manager, current_profile.name):
            continue
        handled_database, audit_store = _handle_database_prompt(
            raw_prompt,
            database_manager,
            approval_manager,
            risk_engine,
            audit_store,
        )
        if handled_database:
            continue
        handled_sqlite, audit_store = _handle_sqlite_prompt(
            raw_prompt,
            sqlite_profile_manager,
            approval_manager,
            risk_engine,
            audit_store,
        )
        if handled_sqlite:
            continue
        handled_mssql, audit_store = _handle_mssql_prompt(
            raw_prompt, mssql_profile_manager, approval_manager, risk_engine, audit_store
        )
        if handled_mssql:
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
        reputation_score = reputation.score if reputation is not None else None
        policy_profiles = (
            [(record.name, profile_manager.get_profile_for_host(record.name)) for record in target_records]
            if target_records and profile_manager is not None
            else [(None, current_profile)]
        )
        policies = [
            (host, profile, policy_engine.evaluate(assessment.level, reputation_score, profile))
            for host, profile in policy_profiles
        ]
        policy = _most_restrictive_policy(policies)
        if target_records:
            for host, profile, result in policies:
                print(f"Host Policy: {host} -> {profile.name} ({result.decision.name})")
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
            final_score = final_reputation.score if final_reputation is not None else None
            final_policies = [
                (host, profile, policy_engine.evaluate(final_assessment.level, final_score, profile))
                for host, profile in policy_profiles
            ]
            final_policy = _most_restrictive_policy(final_policies)
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
