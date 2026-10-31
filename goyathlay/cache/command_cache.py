"""Persistent, history-preserving cache for user-verified commands."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CachedCommand


class CacheError(RuntimeError):
    """Raised when the command cache cannot be safely read or written."""


class CommandCache:
    """Store feedback events and return only currently verified commands."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else Path.home() / ".goyathlay" / "command_cache.json"
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise CacheError("Cache directory and file must not be symbolic links.")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            if self.path.exists():
                self._entries = self._load_entries()
                self.path.chmod(0o600)
            else:
                self._entries: list[CachedCommand] = []
                self._save()
        except OSError as exc:
            raise CacheError(f"Could not initialize command cache: {exc}") from exc

    def get_verified(self, intent: str) -> CachedCommand | None:
        """Return the newest currently verified command for an exact intent.

        A failed outcome supersedes an earlier verification for the same
        intent-command pair. Any dangerous outcome permanently excludes that
        pair from lookup.
        """
        normalized_intent = _normalize_intent(intent)
        latest_by_command: dict[str, CachedCommand] = {}
        dangerous_commands: set[str] = set()
        for entry in self._entries:
            if _normalize_intent(entry.intent) != normalized_intent:
                continue
            if entry.status == "dangerous":
                dangerous_commands.add(entry.command)
            latest_by_command[entry.command] = entry

        for entry in reversed(self._entries):
            if _normalize_intent(entry.intent) != normalized_intent:
                continue
            latest = latest_by_command[entry.command]
            if latest.status == "verified" and entry is latest and entry.command not in dangerous_commands:
                return entry
        return None

    def record_success(self, intent: str, command: str) -> CachedCommand:
        """Record a helpful, successfully executed command as verified."""
        return self._record(intent, command, "verified")

    def record_failure(self, intent: str, command: str) -> CachedCommand:
        """Record a command that executed but did not solve the intent."""
        return self._record(intent, command, "failed")

    def record_dangerous(self, intent: str, command: str) -> CachedCommand:
        """Record a command that must never be reused from this cache."""
        return self._record(intent, command, "dangerous")

    def history(self) -> list[CachedCommand]:
        """Return a copy of all cache events in recorded order."""
        return list(self._entries)

    def _record(self, intent: str, command: str, status: str) -> CachedCommand:
        if not intent.strip():
            raise ValueError("Intent must not be empty.")
        if not command.strip():
            raise ValueError("Command must not be empty.")

        # Ignore consecutive duplicate outcomes while preserving every state change.
        for existing in reversed(self._entries):
            if (
                _normalize_intent(existing.intent) == _normalize_intent(intent)
                and existing.command == command
            ):
                if existing.status == status:
                    return existing
                break

        entry = CachedCommand(intent, command, status, _utc_now())
        self._entries.append(entry)
        try:
            self._save()
        except CacheError:
            self._entries.pop()
            raise
        return entry

    def _load_entries(self) -> list[CachedCommand]:
        try:
            with self.path.open(encoding="utf-8") as stream:
                data: Any = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise CacheError(f"Could not read command cache: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
            raise CacheError("Command cache must contain an 'entries' list.")
        entries: list[CachedCommand] = []
        required = {"intent", "command", "status", "created_at"}
        for index, item in enumerate(data["entries"]):
            if not isinstance(item, dict) or set(item) != required or not all(
                isinstance(item[key], str) for key in required
            ):
                raise CacheError(f"Invalid command cache record at index {index}.")
            try:
                entries.append(CachedCommand(**item))
            except (TypeError, ValueError) as exc:
                raise CacheError(f"Invalid command cache record at index {index}: {exc}") from exc
        return entries

    def _save(self) -> None:
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = stream.name
                os.fchmod(stream.fileno(), 0o600)
                json.dump(
                    {"entries": [entry.__dict__ for entry in self._entries]},
                    stream,
                    indent=2,
                    ensure_ascii=False,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            self.path.chmod(0o600)
        except OSError as exc:
            raise CacheError(f"Could not save command cache: {exc}") from exc
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass


def _normalize_intent(intent: str) -> str:
    return " ".join(intent.split()).casefold()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
