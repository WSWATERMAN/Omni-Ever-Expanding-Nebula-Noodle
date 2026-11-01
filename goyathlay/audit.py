"""Append-only local audit records for approved command execution."""

import fcntl
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditRecord:
    """Immutable details of one approved command execution attempt."""

    timestamp: str
    intent: str
    command: str
    risk_level: str
    approval_result: str
    return_code: int
    success: bool
    host: str | None = None


class AuditStoreError(RuntimeError):
    """Raised when the audit log cannot be safely read or written."""


class AuditStore:
    """Persist immutable execution records as one JSON object per line."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else Path.home() / ".goyathlay" / "audit.jsonl"
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise AuditStoreError("Audit store directory and log must not be symbolic links.")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            os.fchmod(descriptor, 0o600)
            os.close(descriptor)
        except OSError as exc:
            raise AuditStoreError(f"Could not initialize audit store: {exc}") from exc

    def append(self, record: AuditRecord) -> None:
        """Atomically append a complete record without rewriting prior lines."""
        if not isinstance(record, AuditRecord):
            raise TypeError("record must be an AuditRecord.")
        line = (json.dumps(record.__dict__, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        descriptor: int | None = None
        try:
            descriptor = os.open(
                self.path,
                os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0),
            )
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            os.fchmod(descriptor, 0o600)
            view = memoryview(line)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("Audit append made no progress.")
                view = view[written:]
            os.fsync(descriptor)
        except OSError as exc:
            raise AuditStoreError(f"Could not append audit record: {exc}") from exc
        finally:
            if descriptor is not None:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(descriptor)

    def load(self) -> list[AuditRecord]:
        """Return valid records in file order, skipping malformed lines."""
        descriptor: int | None = None
        try:
            descriptor = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "r", encoding="utf-8", errors="replace") as stream:
                descriptor = None
                records: list[AuditRecord] = []
                for line in stream:
                    try:
                        data: Any = json.loads(line)
                        record = _record_from_data(data)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
                    if record is not None:
                        records.append(record)
                return records
        except OSError as exc:
            raise AuditStoreError(f"Could not load audit log: {exc}") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)


def utc_timestamp() -> str:
    """Return the current time as a UTC ISO 8601 timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _record_from_data(data: Any) -> AuditRecord | None:
    legacy_fields = {
        "timestamp",
        "intent",
        "command",
        "risk_level",
        "approval_result",
        "return_code",
        "success",
    }
    fields = legacy_fields | {"host"}
    if not isinstance(data, dict) or set(data) not in (legacy_fields, fields):
        return None
    if not all(isinstance(data[field], str) for field in legacy_fields - {"return_code", "success"}):
        return None
    if type(data["return_code"]) is not int or type(data["success"]) is not bool:
        return None
    if "host" in data and data["host"] is not None and not isinstance(data["host"], str):
        return None
    return AuditRecord(**data)
