"""Generate explicit rollback plans for operations with known compensation."""

import shlex
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class OperationKind(Enum):
    """Operation categories with documented compensating actions."""

    FILE_CHANGE = "file_change"
    PACKAGE_INSTALL = "package_install"
    SERVICE_RESTART = "service_restart"


@dataclass(frozen=True)
class RollbackAction:
    """Description of an operation previously completed by an external actor."""

    kind: OperationKind
    target: str
    backup_path: str | None = None
    package_manager: str | None = None


@dataclass(frozen=True)
class RollbackStep:
    """A suggested compensating operation requiring separate review."""

    target: str
    command: str
    note: str


@dataclass(frozen=True)
class RollbackPlan:
    """Ordered rollback suggestions and operations that cannot be reversed."""

    steps: tuple[RollbackStep, ...]
    blockers: tuple[str, ...]


class RollbackPlanner:
    """Plan compensating commands; deliberately offers no execution method."""

    _PACKAGE_REMOVERS = {
        "apt": "apt-get remove -- {package}",
        "dnf": "dnf remove -- {package}",
        "yum": "yum remove -- {package}",
    }

    def plan(self, actions: Iterable[RollbackAction]) -> RollbackPlan:
        """Create reverse-order suggestions and report missing recovery data."""
        steps: list[RollbackStep] = []
        blockers: list[str] = []
        for action in reversed(tuple(actions)):
            if not isinstance(action, RollbackAction) or not isinstance(action.kind, OperationKind):
                raise TypeError("actions must contain RollbackAction values.")
            target = shlex.quote(action.target)
            if not action.target.strip():
                blockers.append("An operation has an empty target.")
            elif action.kind is OperationKind.FILE_CHANGE:
                if not action.backup_path:
                    blockers.append(f"No backup recorded for file change: {action.target}")
                else:
                    steps.append(RollbackStep(
                        action.target,
                        f"cp -- {shlex.quote(action.backup_path)} {target}",
                        "Restore the recorded backup; verify ownership and permissions before approval.",
                    ))
            elif action.kind is OperationKind.PACKAGE_INSTALL:
                template = self._PACKAGE_REMOVERS.get(action.package_manager or "")
                if template is None:
                    blockers.append(f"Unsupported or missing package manager for: {action.target}")
                else:
                    steps.append(RollbackStep(
                        action.target,
                        template.format(package=target),
                        "Compensating uninstall may remove dependencies or data; inspect before approval.",
                    ))
            elif action.kind is OperationKind.SERVICE_RESTART:
                steps.append(RollbackStep(
                    action.target,
                    f"systemctl restart {target}",
                    "This only restarts the service again; it cannot restore prior runtime state.",
                ))
        return RollbackPlan(tuple(steps), tuple(blockers))
