#!/usr/bin/env python3
"""Interactive, local-first Goyathlay command line application."""

import os
import shlex
import sys
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
    from .feedback import FeedbackStore
    from .ui.banner import render_banner
    from .ui.hotkeys import ConsoleState, HotkeyManager
    from .ui.prompt import read_prompt
    from .ui.statusbar import StatusBar
    from .ui.statusbar import count_test_cases, render_status_output
    from .ui.views import render_database_plan, render_execution_plan
    from .ui.diagnostics import render_engine_diagnostic
    from .healing import HealingManager, HealingError
    from .knowledge import KnowledgeBase, KnowledgeError, KnowledgeStatus
    from .knowledge.migration import migrate_legacy_data
    from .knowledge.review_queue import ReviewQueue
    from .knowledge.grading import GRADE_LABELS, validate_grade
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
    from feedback import FeedbackStore
    from ui.banner import render_banner
    from ui.hotkeys import ConsoleState, HotkeyManager
    from ui.prompt import read_prompt
    from ui.statusbar import StatusBar
    from ui.statusbar import count_test_cases, render_status_output
    from ui.views import render_database_plan, render_execution_plan
    from ui.diagnostics import render_engine_diagnostic
    from healing import HealingManager, HealingError
    from knowledge import KnowledgeBase, KnowledgeError, KnowledgeStatus
    from knowledge.migration import migrate_legacy_data
    from knowledge.review_queue import ReviewQueue
    from knowledge.grading import GRADE_LABELS, validate_grade


APP_VERSION = "1.0.0"


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


def _trainer_feedback(knowledge: KnowledgeBase, intent: str, environment: str,
                      implementation: str, result: str, trainer: str = "local") -> None:
    """Collect a trainer grade and persist it against the candidate."""
    print("TRAINER IMPLEMENTATION REVIEW")
    print(f"Intent:\n{intent}")
    print(f"Generated Command:\n{implementation}")
    print(f"Result:\n{result or '(no output)'}")
    for grade, label in sorted(GRADE_LABELS.items(), reverse=True):
        print(f"{grade} = {label}")
    while True:
        raw_grade = input("Grade (0-5): ").strip()
        try:
            grade = validate_grade(int(raw_grade))
            break
        except (ValueError, TypeError):
            print("Enter a whole number from 0 through 5.")
    notes = input("Optional Note: ").strip()
    entry = knowledge.record_trainer_grade(intent, environment, implementation, grade, notes, trainer)
    print(f"Trainer grade recorded. Average: {entry.trainer_score:.2f}/5")


def _collect_knowledge_review(knowledge: KnowledgeBase | None, intent: str,
                              environment: str, implementation: str, result: str,
                              mode: str, user: UserContext | None = None,
                              kind: str = "shell") -> None:
    """Apply persona RBAC before collecting and persisting a review."""
    active_user = user or UserContext("local", Role.ADMIN)
    rbac = RbacEngine()
    if mode == "trainer":
        if not rbac.authorize_learning(active_user, "grade"):
            print("Trainer grading denied for this role.")
            return
        if knowledge is None:
            print("Trainer feedback cannot be stored because the knowledge base is unavailable.")
            return
        _trainer_feedback(knowledge, intent, environment, implementation, result, active_user.username)
        return
    if not rbac.authorize_learning(active_user, "feedback"):
        print("Operator feedback denied for this role.")
        return
    feedback = FeedbackManager().review(intent, implementation, operator_view=mode == "operator")
    if knowledge is not None:
        knowledge.add_candidate(intent, environment, implementation, kind)
    if knowledge is not None and feedback is not FeedbackResult.SKIPPED:
        knowledge.record_operator_feedback(intent, environment, implementation, feedback.value, kind)


def _handle_knowledge_command(raw: str, knowledge: KnowledgeBase | None,
                              user: UserContext, rbac: RbacEngine,
                              persona: str = "operator") -> bool:
    """Handle knowledge statistics, trainer queue, and SME curation commands."""
    name = raw.strip().casefold()
    if name not in {"knowledge stats", "trainer queue", "sme review"}:
        return False
    if knowledge is None:
        print("Knowledge base is unavailable.")
        return True
    if name == "knowledge stats":
        if persona == "operator":
            print("Knowledge statistics are available in trainer or SME mode.")
            return True
        if not (rbac.authorize_learning(user, "grade") or rbac.authorize_learning(user, "approve")):
            print("Knowledge statistics denied: this role cannot inspect implementation records.")
            return True
        stats = knowledge.stats()
        print(f"Total Entries: {stats['total_entries']}\nApproved Entries: {stats['approved_entries']}\nPending Review: {stats['pending_review']}\nRejected Entries: {stats['rejected_entries']}")
        for label, entries in (("Top Rated Implementations", stats["top_rated"]),
                               ("Lowest Rated Implementations", stats["lowest_rated"])):
            print(f"{label}:")
            for entry in entries:
                print(f"- [{entry.environment}/{entry.type}] {entry.intent}: {entry.implementation} ({entry.score:.2f}) {entry.sme_status}")
        return True
    if name == "trainer queue":
        if persona not in {"trainer", "sme"}:
            print("Trainer queue is available in trainer or SME mode.")
            return True
        if not rbac.authorize_learning(user, "grade"):
            print("Trainer queue denied: this role cannot review implementation quality.")
            return True
        pending = knowledge.list_pending()
        print("Pending SME Review:")
        if not pending:
            print("- Empty")
        for entry in pending:
            print(f"- {entry.intent} [{entry.environment}/{entry.type}]: {entry.implementation} (average grade: {entry.trainer_score if entry.trainer_score is not None else 'ungraded'})")
        return True
    if persona != "sme":
        print("Switch to SME mode with 'mode sme' to review organizational knowledge.")
        return True
    if not rbac.authorize_learning(user, "approve"):
        print("SME review denied: this role cannot approve organizational knowledge.")
        return True
    queue = ReviewQueue(knowledge)
    pending = queue.pending()
    if not pending:
        print("SME review queue is empty.")
        return True
    for entry in pending:
        print("-" * 40)
        print(f"Intent:\n{entry.intent}\nEnvironment:\n{entry.environment}\nGenerated Command:\n{entry.implementation}")
        print(f"Average Grade: {entry.trainer_score if entry.trainer_score is not None else 'Not graded'}")
        total = entry.success_count + entry.failure_count + entry.dangerous_count
        success_rate = f"{entry.success_count / total:.0%}" if total else "Unknown"
        print(f"Operator Success Rate: {success_rate}\nDangerous Reports: {entry.dangerous_count}\nReviews: {entry.trainer_review_count + total}")
        action = input("[A] Approve [R] Reject [E] Replace Command [N] Add Note [S] Skip: ").strip().casefold()
        if action not in {"a", "approve", "r", "reject", "e", "replace", "n", "note", "s", "skip"}:
            print("Unknown action; candidate left pending.")
            continue
        try:
            if action in {"a", "approve"}:
                note = input("Optional Note: ").strip()
                queue.approve(entry, note)
                print("Knowledge approved.")
            elif action in {"r", "reject"}:
                note = input("Reason: ").strip()
                queue.reject(entry, note)
                print("Knowledge rejected.")
            elif action in {"e", "replace"}:
                replacement = input("Replacement implementation: ").strip()
                if replacement:
                    note = input("Optional Note: ").strip()
                    queue.replace(entry, replacement, note)
                    print("Old candidate rejected; replacement added as pending.")
                else:
                    print("Replacement was empty; no change made.")
            elif action in {"n", "note"}:
                queue.add_note(entry, input("Note: ").strip())
                print("Note recorded; candidate remains pending.")
        except (ValueError, KnowledgeError) as exc:
            print(f"Unable to update knowledge: {exc}")
    return True


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
    show_risk: bool = True,
    mode: str = "operator",
    knowledge_base: KnowledgeBase | None = None,
    learning_user: UserContext | None = None,
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
        known = knowledge_base.get_approved(intent, "postgres", "postgres") if knowledge_base else None
        if known:
            query = replace(query, sql=known.implementation)
    except (DatabaseProfileError, ValueError) as exc:
        print(f"Unable to prepare PostgreSQL query:\n{exc}")
        return True, audit_store

    validation = interpreter.validate(query.sql)
    if not validation.allowed:
        print(f"SQL validation blocked execution:\n{validation.reason}")
        return True, audit_store
    assessment = risk_engine.assess(query.sql)
    show_plan = mode in {"review", "debug"} or (assessment.level is RiskLevel.HIGH if mode == "operator" else (assessment.level is not RiskLevel.LOW and show_risk))
    if mode == "operator" and not show_plan:
        print(f"Profile: {profile.name}\nDatabase: {profile.host}:{profile.port}/{profile.database}")
    if show_plan:
        print(render_database_plan(
            engine="PostgreSQL", profile=profile.name, sql=query.sql,
            risk=assessment.level.name, validation="PASSED",
            target=f"{profile.host}:{profile.port}/{profile.database}",
            show_risk=True,
        ))
    try:
        approved, approved_sql = approval_manager.review(query.sql, display_command=not show_plan and mode != "operator")
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
        _collect_knowledge_review(knowledge_base, intent, "postgres", approved_sql,
                                  "\n".join(str(row) for row in result.rows), mode,
                                  learning_user, "postgres")
    except KeyboardInterrupt:
        print("\nExiting Goyathlay.")
    except (FeedbackStoreError, KnowledgeError) as exc:
        print(f"Unable to store database feedback:\n{exc}")
    return True, audit_store


def _handle_sqlite_prompt(
    raw_prompt: str,
    manager: SqliteProfileManager | None,
    approval_manager: ApprovalManager,
    risk_engine: RiskEngine,
    audit_store: AuditStore | None,
    show_risk: bool = True,
    mode: str = "operator",
    knowledge_base: KnowledgeBase | None = None,
    learning_user: UserContext | None = None,
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
        known = knowledge_base.get_approved(intent, "sqlite", "sqlite") if knowledge_base else None
        if known:
            query = replace(query, sql=known.implementation)
    except (SqliteProfileError, ValueError) as exc:
        print(f"Unable to prepare SQLite query:\n{exc}")
        return True, audit_store

    validation = interpreter.validate(query.sql)
    if not validation.allowed:
        print(f"SQL validation blocked execution:\n{validation.reason}")
        return True, audit_store
    assessment = risk_engine.assess(query.sql)
    show_plan = mode in {"review", "debug"} or (assessment.level is RiskLevel.HIGH if mode == "operator" else (assessment.level is not RiskLevel.LOW and show_risk))
    if mode == "operator" and not show_plan:
        print(f"Profile:\n{profile.name}\nDatabase:\n{profile.database}")
    if show_plan:
        print(render_database_plan(
            engine="SQLite", profile=profile.name, sql=query.sql,
            risk=assessment.level.name, validation="PASSED",
            target=profile.database,
            show_risk=True,
        ))
    try:
        approved, approved_sql = approval_manager.review(query.sql, display_command=not show_plan and mode != "operator")
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
        _collect_knowledge_review(knowledge_base, intent, "sqlite", approved_sql,
                                  "\n".join(str(row) for row in result.rows), mode,
                                  learning_user, "sqlite")
    except KeyboardInterrupt:
        print("\nExiting Goyathlay.")
    except (FeedbackStoreError, KnowledgeError) as exc:
        print(f"Unable to store SQLite feedback:\n{exc}")
    return True, audit_store


def _handle_mssql_prompt(
    raw_prompt: str,
    manager: MssqlProfileManager | None,
    approval_manager: ApprovalManager,
    risk_engine: RiskEngine,
    audit_store: AuditStore | None,
    show_risk: bool = True,
    mode: str = "operator",
    knowledge_base: KnowledgeBase | None = None,
    learning_user: UserContext | None = None,
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
        known = knowledge_base.get_approved(intent, "mssql", "mssql") if knowledge_base else None
        if known:
            query = replace(query, sql=known.implementation)
    except (MssqlProfileError, ValueError) as exc:
        print(f"Unable to prepare MSSQL query:\n{exc}")
        return True, audit_store

    validation = interpreter.validate(query.sql)
    if not validation.allowed:
        print(f"SQL validation blocked execution:\n{validation.reason}")
        return True, audit_store
    assessment = risk_engine.assess(query.sql)
    show_plan = mode in {"review", "debug"} or (assessment.level is RiskLevel.HIGH if mode == "operator" else (assessment.level is not RiskLevel.LOW and show_risk))
    if mode == "operator" and not show_plan:
        print(f"Profile: {profile.name}\nDatabase: {profile.server}:{profile.port}/{profile.database}")
    if show_plan:
        print(render_database_plan(
            engine="Microsoft SQL Server", profile=profile.name, sql=query.sql,
            risk=assessment.level.name, validation="PASSED",
            target=f"{profile.server}:{profile.port}/{profile.database}",
            show_risk=True,
        ))
    try:
        approved, approved_sql = approval_manager.review(query.sql, display_command=not show_plan and mode != "operator")
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
        _collect_knowledge_review(knowledge_base, intent, "mssql", approved_sql,
                                  "\n".join(str(row) for row in result.rows), mode,
                                  learning_user, "mssql")
    except KeyboardInterrupt:
        print("\nExiting Goyathlay.")
    except (FeedbackStoreError, KnowledgeError) as exc:
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
    *,
    display_decision: bool = True,
) -> AuthorizationDecision:
    """Display the role decision and obtain any required explicit override."""
    decision = engine.authorize(user, risk_level)
    if display_decision:
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
    knowledge: KnowledgeBase | None = None,
    intent: str | None = None,
    environment: str = "local",
    kind: str = "shell",
) -> CommandReputation | None:
    """Return combined operator/trainer/SME reputation, with legacy fallback."""
    legacy: CommandReputation | None = None
    try:
        legacy = engine.get_reputation(command) if engine is not None else None
    except FeedbackStoreError as exc:
        print(f"Reputation unavailable:\n{exc}")
    if knowledge is not None and intent is not None:
        entry = knowledge.get_candidate(intent, environment, command, kind)
        if entry is not None and entry.reputation_score is not None:
            return CommandReputation(
                command, entry.success_count, entry.failure_count,
                entry.dangerous_count, entry.reputation_score,
            )
    return legacy


def _display_command_policy(
    command: str,
    risk_level: RiskLevel,
    risk_reasons: list[str],
    reputation: CommandReputation | None,
    policy: PolicyResult,
    target_host: str | None = None,
    profile: PolicyProfile | None = None,
    intent: str = "(see prompt)",
    role: str = "ADMIN",
    show_risk: bool = True,
) -> None:
    """Display the assessed command, its history, and the policy outcome."""
    print(render_execution_plan(
        intent=intent, command=command,
        targets=tuple(item.strip() for item in target_host.split(",")) if target_host else (),
        engine=os.environ.get("GOYATHLAY_OLLAMA_MODEL", "qwen2.5-coder:14b"),
        profile=profile.name if profile else "unavailable", role=role,
        risk=risk_level.name, reasons=risk_reasons,
        reputation=reputation.score if reputation else None,
        policy=policy.decision.name.replace("_", " "), policy_reasons=policy.reasons,
        show_risk=show_risk,
    ))


def _update_console_health(state: ConsoleState, plan: dict[str, object]) -> None:
    """Set a concise health indicator from a read-only healing scan result."""
    issues = plan.get("issues", [])
    if not isinstance(issues, list) or not issues:
        state.health = "HEALTHY"
        state.health_message = "All local checks passed"
        return
    names = [str(item.get("issue", "Unknown issue")) for item in issues if isinstance(item, dict)]
    ollama_unavailable = next(
        (name for name in names if "ollama executable" in name.casefold() or "ollama daemon" in name.casefold()),
        None,
    )
    if ollama_unavailable:
        state.health = "CRITICAL"
        state.health_message = "Ollama unavailable"
        return
    model_issue = next((name for name in names if "model" in name.casefold() and "missing" in name.casefold()), None)
    if model_issue:
        model = model_issue.removeprefix("Missing ").removesuffix(" model")
        state.health = "DEGRADED"
        state.health_message = f"Missing model {model}"
        return
    if names and "missing ollama package" in names[0].casefold():
        state.health = "DEGRADED"
        state.health_message = "Ollama Python package missing"
        return
    state.health = "DEGRADED"
    state.health_message = names[0] if names else "Healing scan unavailable"


def _show_decision_details(state: ConsoleState, risk_level: RiskLevel) -> bool:
    """Gate verbose decision details behind risk or an explicit display mode."""
    if state.mode in {"review", "debug"}:
        return True
    if state.persona == "operator":
        return risk_level is RiskLevel.HIGH and state.show_risk
    return risk_level is not RiskLevel.LOW and state.show_risk


def _handle_operator_command(
    command: str, *, profile_manager: ProfileManager | None,
    current_profile: PolicyProfile | None, host_inventory: HostInventory | None,
    command_cache: CommandCache | None, audit_store: AuditStore | None,
    show_audit_details: bool = False,
    cache_enabled: bool = True,
    healing_manager: HealingManager | None = None,
    console_state: ConsoleState | None = None,
    role: str = "ADMIN",
    user_context: UserContext | None = None,
    rbac_engine: RbacEngine | None = None,
) -> bool:
    """Handle the console's status, help, inventory, audit, and history views."""
    name = command.strip().casefold()
    if name == "help":
        print("Core Commands:\nstatus\nmode [operator|trainer|sme|review|debug]\nknowledge stats\ntrainer queue\nsme review\nprofiles\nprofile <name>\nheal dry-run\nheal review\nheal auto --dry-run\nheal auto\nheal save-plan\n\nHosts:\ninventory\nhosts\ngroups\n\nDatabase:\ndb profiles\ndb profile <name>\nsqlite profiles\nmssql profiles\n\nMaintenance:\nmaintenance\nmaintenance enable\nmaintenance disable\n\nSecurity:\nblocklist\naudit\nhistory\n\nType exit or quit to leave.")
        return True
    if name == "mode":
        print(f"Display Mode: {console_state.mode if console_state else 'operator'}")
        return True
    if name.startswith("mode "):
        selected = name.split(maxsplit=1)[1]
        if selected not in {"operator", "review", "debug", "trainer", "sme"}:
            print("Usage: mode operator | mode trainer | mode sme | mode review | mode debug")
        elif selected in {"trainer", "sme"} and user_context is not None and rbac_engine is not None and not rbac_engine.authorize_learning(
            user_context, "grade" if selected == "trainer" else "approve"
        ):
            print(f"RBAC denied: role {user_context.role.name} cannot enter {selected} mode.")
        elif console_state is None:
            print("Display mode is unavailable.")
        else:
            console_state.mode = selected
            if selected in {"operator", "trainer", "sme"}:
                console_state.persona = selected
            console_state.notice = f"Mode: {selected}"
            print(f"Persona: {console_state.persona} (display mode: {console_state.mode})")
        return True
    if name == "status":
        healing_status: dict[str, object] = {}
        try:
            plan = (healing_manager or HealingManager()).scan()
            if console_state is not None:
                _update_console_health(console_state, plan)
            healing_status = {
                "health": console_state.health if console_state else ("DEGRADED" if plan["issues"] else "HEALTHY"),
                "outstanding_issues": len(plan["issues"]),
                "last_healing_scan": plan["generated_at"],
            }
        except HealingError:
            if console_state is not None:
                console_state.health = "DEGRADED"
                console_state.health_message = "Health scan unavailable"
            healing_status = {"health": "UNKNOWN", "outstanding_issues": 0, "last_healing_scan": "Unavailable"}
        try:
            host_count = len(host_inventory.list_hosts()) if host_inventory else 0
            group_count = len(host_inventory.list_groups()) if host_inventory else 0
            profile_count = len(profile_manager.list_profiles()) if profile_manager else 0
        except Exception:
            host_count = group_count = profile_count = 0
        print(render_status_output(
            engine=os.environ.get("GOYATHLAY_OLLAMA_MODEL", "qwen2.5-coder:14b"),
            profile=current_profile.name if current_profile else "unavailable",
            role=role, cache_enabled=cache_enabled,
            audit_enabled=True, tofu_enabled=True, hosts=host_count,
            groups=group_count, profiles=profile_count,
            test_count=count_test_cases(), version=APP_VERSION,
            **healing_status,
        ))
        return True
    if name in {"inventory", "hosts", "groups"}:
        if host_inventory is None:
            print("Host inventory is unavailable.")
            return True
        if name in {"inventory", "hosts"}:
            records = host_inventory.list_hosts()
            print(f"Hosts: {len(records)}")
            for record in records:
                print(f"- {record.name}: {record.username}@{record.hostname}:{record.port}")
        if name in {"inventory", "groups"}:
            groups = host_inventory.list_groups()
            print(f"Groups: {len(groups)}")
            for group, members in groups.items():
                print(f"- {group}: {', '.join(members)}")
        return True
    if name == "audit":
        try:
            store = audit_store or AuditStore()
            records = store.load()
            print("Audit History:")
            if show_audit_details:
                for record in records[-20:]:
                    print(f"- {record.timestamp} {record.approval_result} rc={record.return_code} {record.command}")
            else:
                passed = sum(record.success for record in records)
                print(f"Records: {len(records)} | Successful: {passed} | Failed: {len(records) - passed}")
            if not records:
                print("No audit records.")
        except Exception as exc:
            print(f"Audit history unavailable:\n{exc}")
        return True
    if name == "history":
        try:
            records = FeedbackStore().load_history()
            print("Feedback History:")
            for record in records[-20:]:
                print(f"- {record['timestamp']} {record['result']} {record['command']}")
            if not records:
                print("No feedback records.")
        except Exception as exc:
            print(f"Feedback history unavailable:\n{exc}")
        return True
    return False


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
    if sys.argv[1:] == ["--version"]:
        print(f"Goyathlay v{APP_VERSION}")
        return
    healing_args = sys.argv[1:]
    if healing_args in (["--heal-auto", "--dry-run"], ["heal", "dry-run"], ["heal", "auto", "--dry-run"]):
        manager = HealingManager()
        print(manager.render(manager.scan()))
        return
    if healing_args in (["heal", "review"], ["heal", "auto"], ["heal", "save-plan"]):
        manager = HealingManager()
        try:
            plan = manager.scan()
            if healing_args == ["heal", "save-plan"]:
                print(f"Healing plan saved to {manager.save_plan(plan)}")
                print(manager.render(plan))
            elif healing_args == ["heal", "review"]:
                print(manager.render(plan))
                print("Reviewing proposed repairs. Each repair requires a separate approval.")
                print(manager.render(manager.review(plan), dry_run=False))
            else:
                print(manager.render(manager.auto_heal(plan), dry_run=False))
        except (HealingError, KeyboardInterrupt, EOFError) as exc:
            if isinstance(exc, (KeyboardInterrupt, EOFError)):
                print("\nHealing cancelled.")
            else:
                print(f"Healing failed: {exc}")
        return
    provider = None
    try:
        ollama_error = _check_ollama_installation()
    except Exception as exc:
        ollama_error = exc
    if ollama_error:
        print(render_engine_diagnostic(
            ollama_error,
            model=os.environ.get("GOYATHLAY_OLLAMA_MODEL", "qwen2.5-coder:14b"),
        ))
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
        knowledge_base = KnowledgeBase()
        migration = migrate_legacy_data(knowledge_base)
        if not migration["already_migrated"] and (migration["imported_candidates"] or migration["imported_feedback"]):
            print(f"Imported legacy learning history: {migration['imported_candidates']} cache entries, {migration['imported_feedback']} feedback events (all pending SME review).")
    except KnowledgeError as exc:
        knowledge_base = None
        print(f"Knowledge base unavailable:\n{exc}")
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

    try:
        profile_names = [item.name for item in profile_manager.list_profiles()] if profile_manager else []
    except Exception:
        profile_names = []
    console_state = ConsoleState(
        profile_manager=profile_manager,
        current_profile=current_profile,
        profile_names=profile_names,
        inventory=host_inventory,
        engine=os.environ.get("GOYATHLAY_OLLAMA_MODEL", "qwen2.5-coder:14b"),
        role=user_context.role.name,
    )
    hotkeys = HotkeyManager(console_state)
    statusbar = StatusBar(console_state)
    healing_manager = HealingManager()
    try:
        _update_console_health(console_state, healing_manager.scan())
    except HealingError:
        console_state.health = "DEGRADED"
        console_state.health_message = "Health scan unavailable"
    print(render_banner(
        engine=console_state.engine,
        profile=current_profile.name if current_profile else "unavailable",
        role=user_context.role.name,
        audit_enabled=True,
        tofu_enabled=True,
    ))
    print("Type 'help' for commands, 'mode trainer' for implementation grading, 'mode sme' for curation, or 'exit' to leave.")

    while True:
        try:
            raw_prompt = read_prompt(
                current_profile.name if current_profile else "unavailable",
                hotkeys=hotkeys,
                statusbar=statusbar,
            ).strip()
        except KeyboardInterrupt:
            print("\nExiting Goyathlay.")
            return

        current_profile = console_state.current_profile
        if raw_prompt.casefold() in ("exit", "quit"):
            return
        if not raw_prompt:
            continue
        if raw_prompt.casefold() in {"heal dry-run", "heal auto --dry-run"}:
            try:
                healing_plan = healing_manager.scan()
                _update_console_health(console_state, healing_plan)
                print(healing_manager.render(healing_plan))
            except HealingError as exc:
                print(f"Healing diagnostics failed: {exc}")
            continue
        if raw_prompt.casefold() in {"heal review", "heal auto", "heal save-plan"}:
            try:
                healing_plan = healing_manager.scan()
                _update_console_health(console_state, healing_plan)
                if raw_prompt.casefold() == "heal save-plan":
                    print(f"Healing plan saved to {healing_manager.save_plan(healing_plan)}")
                    print(healing_manager.render(healing_plan))
                elif raw_prompt.casefold() == "heal review":
                    print(healing_manager.render(healing_plan))
                    print("Reviewing proposed repairs. Each repair requires a separate approval.")
                    print(healing_manager.render(healing_manager.review(healing_plan), dry_run=False))
                else:
                    print(healing_manager.render(healing_manager.auto_heal(healing_plan), dry_run=False))
            except (HealingError, KeyboardInterrupt, EOFError) as exc:
                if isinstance(exc, (KeyboardInterrupt, EOFError)):
                    print("\nHealing cancelled.")
                else:
                    print(f"Healing failed: {exc}")
            continue
        if _handle_operator_command(
            raw_prompt, profile_manager=profile_manager, current_profile=current_profile,
            host_inventory=host_inventory, command_cache=command_cache, audit_store=audit_store,
            show_audit_details=console_state.show_audit_details,
            cache_enabled=command_cache is not None and not console_state.cache_bypass,
            healing_manager=healing_manager,
            console_state=console_state,
            role=user_context.role.name,
            user_context=user_context,
            rbac_engine=rbac_engine,
        ):
            continue
        if _handle_knowledge_command(raw_prompt, knowledge_base, user_context, rbac_engine,
                                     console_state.persona):
            continue
        if console_state.persona == "sme":
            print("SME mode is for knowledge review. Use 'sme review', 'knowledge stats', or switch with 'mode operator'.")
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
                if _show_decision_details(console_state, risk.level):
                    print(render_plan(plan))
                else:
                    print(f"Command:\n{generated}")
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
                    console_state.current_profile = current_profile
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
        if console_state.mode == "debug":
            print("Maintenance: ALLOW")
        handled_database, audit_store = _handle_database_prompt(
            raw_prompt,
            database_manager,
            approval_manager,
            risk_engine,
            audit_store,
            console_state.show_risk,
            console_state.mode,
            knowledge_base,
            user_context,
        )
        if handled_database:
            continue
        handled_sqlite, audit_store = _handle_sqlite_prompt(
            raw_prompt,
            sqlite_profile_manager,
            approval_manager,
            risk_engine,
            audit_store,
            console_state.show_risk,
            console_state.mode,
            knowledge_base,
            user_context,
        )
        if handled_sqlite:
            continue
        handled_mssql, audit_store = _handle_mssql_prompt(
            raw_prompt, mssql_profile_manager, approval_manager, risk_engine, audit_store,
            console_state.show_risk,
            console_state.mode,
            knowledge_base,
            user_context,
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
            cache_state = "BYPASS" if console_state.cache_bypass else "UNAVAILABLE"
            command_source = "Ollama"
            environment = "remote" if target_name is not None else os.environ.get("GOYATHLAY_ENVIRONMENT", "local")
            known_entry = (
                knowledge_base.get_approved(prompt, environment, "shell")
                if knowledge_base is not None and not console_state.cache_bypass else None
            )
            if known_entry is not None:
                command = clean_command(known_entry.implementation)
                command_source = "Approved organizational knowledge"
                cache_state = "APPROVED KNOWLEDGE HIT"
            else:
                if console_state.ai_bypass:
                    if console_state.mode == "debug":
                        print(f"Cache: {cache_state}\nCommand Source: Generation bypassed")
                    print("AI generation bypass is enabled and no verified cached command was selected.")
                    continue
                if provider is None:
                    provider = _create_provider()
                generated_command = provider.generate_command(prompt)
                command = clean_command(generated_command)
            if console_state.mode == "debug":
                print(f"Cache: {cache_state}\nCommand Source: {command_source}")
        except KeyboardInterrupt:
            print("\nExiting Goyathlay.")
            return
        except Exception as exc:
            lowered_error = str(exc).casefold()
            if "model" in lowered_error and "not found" in lowered_error:
                console_state.health = "DEGRADED"
                console_state.health_message = f"Missing model {console_state.engine}"
            elif "ollama daemon" in lowered_error or "ollama service" in lowered_error or "unreachable" in lowered_error:
                console_state.health = "CRITICAL"
                console_state.health_message = "Ollama unavailable"
            print(render_engine_diagnostic(exc, model=console_state.engine))
            continue

        blocked_rule = blocklist.blocked_by(command)
        if blocked_rule is not None:
            if console_state.mode == "debug":
                print("Blocklist: BLOCK")
            _display_blocked_command(blocked_rule, command)
            continue
        if console_state.mode == "debug":
            print("Blocklist: ALLOW")
        assessment = risk_engine.assess(command)

        reputation = _get_reputation(reputation_engine, command)
        show_details = _show_decision_details(console_state, assessment.level)
        authorization = _authorize_command(
            rbac_engine, user_context, assessment.level,
            display_decision=show_details,
        )
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
        if target_records and show_details:
            for host, profile, result in policies:
                print(f"Host Policy: {host} -> {profile.name} ({result.decision.name})")
        if show_details:
            _display_command_policy(
                command,
                assessment.level,
                assessment.reasons,
                reputation,
                policy,
                target_display,
                current_profile,
                intent=prompt,
                role=user_context.role.name,
                show_risk=True,
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

            approved, approved_command = approval_manager.review(
                command,
                display_command=not (show_details or (
                    console_state.persona == "operator"
                    and assessment.level is not RiskLevel.HIGH
                    and console_state.mode not in {"review", "debug"}
                )),
            )
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
            final_show_details = _show_decision_details(console_state, final_assessment.level)
            final_authorization = _authorize_command(
                rbac_engine, user_context, final_assessment.level,
                display_decision=final_show_details,
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
            if final_show_details:
                _display_command_policy(
                    approved_command,
                    final_assessment.level,
                    final_assessment.reasons,
                    final_reputation,
                    final_policy,
                    target_display,
                    current_profile,
                    intent=prompt,
                    role=user_context.role.name,
                    show_risk=True,
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
        if console_state.mode == "debug":
            print("Maintenance: ALLOW (rechecked before execution)")

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

        result_text = "\n".join(
            part for part in (
                result.stdout if fanout_results is None else "\n".join(item.stdout for item in fanout_results),
                result.stderr if fanout_results is None else "\n".join(item.stderr for item in fanout_results),
            ) if part
        )
        try:
            if knowledge_base is not None:
                _collect_knowledge_review(
                    knowledge_base, prompt,
                    "remote" if target_name is not None else os.environ.get("GOYATHLAY_ENVIRONMENT", "local"),
                    approved_command, result_text, console_state.persona,
                    user_context, "shell",
                )
            else:
                FeedbackManager().review(cache_intent, approved_command,
                                         operator_view=console_state.persona == "operator")
        except KeyboardInterrupt:
            print("\nExiting Goyathlay.")
            return
        except (FeedbackStoreError, KnowledgeError, ValueError) as exc:
            print(f"Unable to store learning feedback:\n{exc}")


if __name__ == "__main__":
    main()
