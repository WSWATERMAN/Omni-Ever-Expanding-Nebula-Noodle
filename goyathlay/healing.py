"""Read-only healing plans with explicit, auditable repair approval."""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}


def utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ProposedRepair:
    """Describe an issue and a possible repair without performing it."""

    issue: str
    repair: str
    command: str | None
    risk_level: str
    requires_network: bool

    def __post_init__(self) -> None:
        if not self.issue.strip() or not self.repair.strip():
            raise ValueError("Issue and repair descriptions must not be empty.")
        if self.risk_level not in RISK_LEVELS:
            raise ValueError("risk_level must be LOW, MEDIUM, or HIGH.")
        if type(self.requires_network) is not bool:
            raise TypeError("requires_network must be a boolean.")
        if self.command is not None and not self.command.strip():
            raise ValueError("command must be None or a non-empty string.")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the repair using the report's `risk` field."""
        values = asdict(self)
        values["risk"] = values.pop("risk_level")
        return values


@dataclass(frozen=True)
class HealingAuditRecord:
    """One append-only audit event for a considered healing action."""

    timestamp: str
    issue: str
    repair: str
    mode: str


class HealingError(RuntimeError):
    """Raised when a healing report, audit event, or approved repair fails."""


class HealingManager:
    """Diagnose local Goyathlay setup and run only explicitly authorized repairs.

    Construction and ``scan`` are read-only. Persistence and repair methods are
    separate so a dry-run cannot create directories, adjust permissions, or
    invoke package/model installation commands.
    """

    def __init__(
        self,
        *,
        home: str | Path | None = None,
        project_root: str | Path | None = None,
        model: str | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        popen: Callable[..., Any] = subprocess.Popen,
        input_fn: Callable[[str], str] = input,
        emit: Callable[[str], None] = print,
        module_available: Callable[[str], bool] | None = None,
        which: Callable[[str], str | None] = shutil.which,
    ) -> None:
        """Configure paths and injectable system interfaces without touching disk."""
        self.home = Path(home).expanduser() if home is not None else Path.home()
        self.config_dir = self.home / ".goyathlay"
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[1]
        self.model = model or os.environ.get("GOYATHLAY_OLLAMA_MODEL", "qwen2.5-coder:14b")
        self.runner = runner
        self.popen = popen
        self.input_fn = input_fn
        self.emit = emit
        self.module_available = module_available or self._module_available
        self.which = which
        self.report_path = self.config_dir / "healing-plan.json"
        self.audit_path = self.config_dir / "healing-audit.jsonl"
        self._last_plan: dict[str, Any] | None = None

    @staticmethod
    def _module_available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            return False

    def scan(self) -> dict[str, Any]:
        """Inspect runtime and selected config files without creating or changing anything."""
        repairs: list[ProposedRepair] = []
        if not self.module_available("ollama"):
            repairs.append(ProposedRepair(
                issue="Missing Ollama package",
                repair="Install Python package",
                command=f"{sys.executable} -m pip install ollama",
                risk_level="LOW",
                requires_network=True,
            ))

        ollama = self.which("ollama")
        model_list = ""
        daemon_ready = False
        if not ollama:
            repairs.append(ProposedRepair(
                issue="Missing Ollama executable",
                repair="Install the local Ollama runtime",
                command=None,
                risk_level="MEDIUM",
                requires_network=True,
            ))
        else:
            try:
                result = self.runner(
                    [ollama, "list"], capture_output=True, text=True,
                    check=False, timeout=10,
                )
                daemon_ready = result.returncode == 0
                model_list = result.stdout or ""
            except (OSError, subprocess.TimeoutExpired):
                daemon_ready = False
            if not daemon_ready:
                repairs.append(ProposedRepair(
                    issue="Ollama daemon is not responding",
                    repair="Start the local Ollama daemon",
                    command="ollama serve",
                    risk_level="LOW",
                    requires_network=False,
                ))
            elif not self._model_is_listed(model_list, self.model):
                repairs.append(ProposedRepair(
                    issue=f"Missing {self.model} model",
                    repair="Download the configured local model",
                    command=f"ollama pull {self.model}",
                    risk_level="LOW",
                    requires_network=True,
                ))

        self._check_inventory(repairs)
        self._check_database_profile_store(repairs)
        self._check_policy_profile_store(repairs)
        self._check_trust_store(repairs)
        self._check_auth_store(repairs)
        plan = {"generated_at": utc_timestamp(), "issues": [repair.to_dict() for repair in repairs]}
        self._last_plan = plan
        return plan

    @staticmethod
    def _model_is_listed(output: str, model: str) -> bool:
        for line in output.splitlines()[1:]:
            fields = line.split()
            if fields and fields[0] == model:
                return True
        return False

    def _check_inventory(self, repairs: list[ProposedRepair]) -> None:
        path = self.config_dir / "inventory.json"
        if path.is_symlink():
            repairs.append(ProposedRepair(
                "Unsafe inventory path", "Review and remove the symbolic link manually",
                None, "HIGH", False,
            ))
            return
        if not path.exists():
            repairs.append(ProposedRepair(
                "Missing inventory file", "Create default inventory.json", None, "LOW", False,
            ))
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            valid = (
                isinstance(data, dict) and set(data) == {"hosts", "groups"}
                and isinstance(data["hosts"], dict) and isinstance(data["groups"], dict)
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            valid = False
        if not valid:
            repairs.append(ProposedRepair(
                "Broken inventory file",
                "Back up the file and repair its JSON/host records manually",
                None, "HIGH", False,
            ))

    def _check_database_profile_store(self, repairs: list[ProposedRepair]) -> None:
        path = self.config_dir / "db_profiles.json"
        if path.is_symlink():
            repairs.append(ProposedRepair(
                "Unsafe database profile path", "Review the symbolic link manually",
                None, "HIGH", False,
            ))
            return
        if not path.exists():
            repairs.append(ProposedRepair(
                "Missing database profile store",
                "Create an empty PostgreSQL profile store; connection details remain operator-managed",
                None, "LOW", False,
            ))
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            valid = (
                isinstance(data, dict) and set(data) == {"default", "profiles"}
                and isinstance(data["profiles"], dict)
                and (data["default"] is None or isinstance(data["default"], str))
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            valid = False
            data = {}
        if not valid:
            repairs.append(ProposedRepair(
                "Broken database profile store",
                "Preserve the current file and repair its profile JSON manually",
                None, "HIGH", False,
            ))
        elif data["default"] is None:
            repairs.append(ProposedRepair(
                "Missing database profile",
                "Configure a PostgreSQL connection profile with an operator-approved read-only account",
                None, "LOW", False,
            ))

    def _check_policy_profile_store(self, repairs: list[ProposedRepair]) -> None:
        """Inspect policy profiles without invoking their auto-creating manager."""
        path = self.config_dir / "profiles.json"
        if path.is_symlink():
            repairs.append(ProposedRepair(
                "Unsafe policy profile path", "Review the symbolic link manually",
                None, "HIGH", False,
            ))
            return
        if not path.exists():
            repairs.append(ProposedRepair(
                "Missing policy profile store", "Create default policy profiles",
                None, "LOW", False,
            ))
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            valid = (
                isinstance(data, dict) and isinstance(data.get("default"), str)
                and isinstance(data.get("profiles"), dict)
                and data["default"] in data["profiles"]
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            valid = False
        if not valid:
            repairs.append(ProposedRepair(
                "Broken policy profile store",
                "Preserve the current file and repair its profile JSON manually",
                None, "HIGH", False,
            ))

    def _check_trust_store(self, repairs: list[ProposedRepair]) -> None:
        """Flag damaged trust data for manual review; never propose replacement."""
        self._check_json_object_file(
            repairs, "trust_store.json", "hosts", "SSH trust store", "HIGH",
            "Preserve and manually review host fingerprints; do not replace trust silently",
        )

    def _check_auth_store(self, repairs: list[ProposedRepair]) -> None:
        """Flag damaged authentication data as a high-risk manual repair."""
        self._check_json_object_file(
            repairs, "users.json", "users", "authentication data", "HIGH",
            "Back up and manually recover authentication records; never replace silently",
        )

    def _check_json_object_file(
        self, repairs: list[ProposedRepair], filename: str, key: str,
        label: str, risk: str, repair: str,
    ) -> None:
        path = self.config_dir / filename
        if not path.exists() and not path.is_symlink():
            return
        valid = False
        if not path.is_symlink():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                valid = isinstance(data, dict) and isinstance(data.get(key), dict)
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        if not valid:
            repairs.append(ProposedRepair(
                f"Unsafe or broken {label}", repair, None, risk, False,
            ))

    def render(self, plan: dict[str, Any] | None = None, *, dry_run: bool = True) -> str:
        """Format a plan for terminal review without persisting it."""
        plan = plan or self._last_plan or self.scan()
        issues = plan.get("issues", [])
        lines = ["-" * 40, "HEALING DRY RUN", "-" * 40, "", f"Issues Found: {len(issues)}", ""]
        for index, issue in enumerate(issues, start=1):
            lines.extend([
                f"{index}.", "", "Issue:", str(issue["issue"]), "", "Repair:",
                str(issue["repair"]), "", "Command:", str(issue["command"] or "Manual / no command"),
                "", f"Risk: {issue['risk']}",
            ])
            if issue.get("requires_network"):
                lines.append("Network: Required")
            lines.append("\n" + "-" * 40)
        lines.extend(["", "No changes were made." if dry_run else "Healing scan complete.", "=" * 40])
        return "\n".join(lines)

    def save_plan(self, plan: dict[str, Any] | None = None) -> Path:
        """Persist a plan after an explicit non-dry-run request, using an atomic write."""
        plan = plan or self._last_plan or self.scan()
        self._ensure_safe_config_directory()
        if self.report_path.is_symlink():
            raise HealingError("Refusing to replace a symbolic link at the healing plan path.")
        temporary = self.report_path.with_name(f".{self.report_path.name}.{os.getpid()}.tmp")
        try:
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(plan, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.report_path)
            self.report_path.chmod(0o600)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise HealingError(f"Could not write healing plan: {exc}") from exc
        return self.report_path

    def audit_record(self, issue: str, repair: str, mode: str) -> HealingAuditRecord:
        """Construct an audit record; construction alone has no side effects."""
        if mode not in {"interactive", "auto", "dry-run", "review"}:
            raise ValueError("Unknown healing audit mode.")
        return HealingAuditRecord(utc_timestamp(), issue, repair, mode)

    def append_audit(self, record: HealingAuditRecord) -> None:
        """Append one healing audit record to a private JSON Lines file."""
        if not isinstance(record, HealingAuditRecord):
            raise TypeError("record must be a HealingAuditRecord.")
        self._ensure_safe_config_directory()
        if self.audit_path.is_symlink():
            raise HealingError("Refusing to append to a symbolic link at the healing audit path.")
        payload = (json.dumps(asdict(record), ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        try:
            descriptor = os.open(
                self.audit_path,
                os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                os.fchmod(descriptor, 0o600)
                if os.write(descriptor, payload) != len(payload):
                    raise OSError("Incomplete healing audit append.")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise HealingError(f"Could not append healing audit record: {exc}") from exc

    def read_audit(self) -> list[HealingAuditRecord]:
        """Read valid healing audit rows without changing the file."""
        if not self.audit_path.exists():
            return []
        if self.audit_path.is_symlink():
            raise HealingError("Refusing to read a symbolic link at the healing audit path.")
        records: list[HealingAuditRecord] = []
        try:
            with self.audit_path.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        item = json.loads(line)
                        if set(item) == {"timestamp", "issue", "repair", "mode"}:
                            records.append(HealingAuditRecord(**item))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
        except OSError as exc:
            raise HealingError(f"Could not read healing audit log: {exc}") from exc
        return records

    def review(self, plan: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ask for each repair separately and execute only individually approved actions."""
        plan = plan or self._last_plan or self.scan()
        report = self.save_plan(plan)
        self.emit(f"Healing plan saved to {report}")
        for number, issue in enumerate(plan.get("issues", []), start=1):
            self.emit(f"\nRepair #{number}\n{issue['repair']}?\n[Y/N]")
            approved = self.input_fn("Selection: ").strip().casefold() in {"y", "yes"}
            self.append_audit(self.audit_record(issue["issue"], issue["repair"], "review"))
            if approved:
                self._apply(issue)
        return self.scan()

    def auto_heal(self, plan: dict[str, Any] | None = None) -> dict[str, Any]:
        """Apply LOW/MEDIUM repairs; require explicit confirmation for every HIGH repair."""
        plan = plan or self._last_plan or self.scan()
        self.save_plan(plan)
        for number, issue in enumerate(plan.get("issues", []), start=1):
            approved = issue["risk"] != "HIGH"
            if issue["risk"] == "HIGH":
                self.emit(f"High-risk repair #{number}: {issue['repair']}")
                approved = self.input_fn("Approve this high-risk repair? [Y/N]: ").strip().casefold() in {"y", "yes"}
            self.append_audit(self.audit_record(issue["issue"], issue["repair"], "auto"))
            if approved:
                self._apply(issue)
        return self.scan()

    def _apply(self, issue: dict[str, Any]) -> bool:
        """Run one recognized repair after approval; never pass a shell string."""
        command = issue.get("command")
        if command:
            try:
                arguments = shlex.split(command)
            except ValueError as exc:
                raise HealingError(f"Invalid proposed repair command: {exc}") from exc
            if arguments == [sys.executable, "-m", "pip", "install", "ollama"]:
                args = [sys.executable, "-m", "pip", "install", "ollama"]
            elif arguments == ["ollama", "pull", self.model]:
                args = ["ollama", "pull", self.model]
            elif arguments == ["ollama", "serve"]:
                try:
                    self.popen(["ollama", "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
                    return True
                except OSError as exc:
                    raise HealingError(f"Could not start Ollama daemon: {exc}") from exc
            else:
                raise HealingError("Repair command is not in the approved local repair allowlist.")
            result = self.runner(args, capture_output=True, text=True, check=False, timeout=600)
            if result.returncode != 0:
                raise HealingError((result.stderr or result.stdout or "Repair command failed.").strip())
            return True

        issue_name = issue.get("issue", "")
        try:
            if issue_name == "Missing inventory file":
                from .inventory import HostInventory
                HostInventory(self.config_dir / "inventory.json")
                return True
            if issue_name == "Missing database profile store":
                from .db.profiles import DbProfileStore
                DbProfileStore(self.config_dir / "db_profiles.json")
                return True
            if issue_name == "Missing policy profile store":
                from .profiles import ProfileManager
                ProfileManager(self.config_dir / "profiles.json")
                return True
        except Exception as exc:
            raise HealingError(f"Approved repair failed: {exc}") from exc
        self.emit("No automatic repair is available for this issue; no change was made.")
        return False

    def _ensure_safe_config_directory(self) -> None:
        if self.config_dir.is_symlink():
            raise HealingError("Refusing to use a symbolic link as the Goyathlay configuration directory.")
        self.config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.config_dir.chmod(0o700)
