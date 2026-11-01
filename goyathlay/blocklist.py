"""Persistent local command blocklist with exact and explicit prefix rules."""

import json
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any


class BlocklistError(RuntimeError):
    """Raised when blocklist data is invalid or cannot be safely stored."""


class BlockDecision(Enum):
    """Whether a command matches a configured block rule."""

    ALLOW = "allow"
    BLOCK = "block"


_DEFAULT_COMMANDS = ["rm -rf /", "mkfs", ":(){ :|:& };:", "dd if="]


class CommandBlocklist:
    """Store exact command rules and wildcard-ended prefix rules."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Load an existing blocklist or create its private default file."""
        self.path = (
            Path(path).expanduser()
            if path is not None
            else Path.home() / ".goyathlay" / "blocklist.json"
        )
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise BlocklistError("Blocklist directory and file must not be symbolic links.")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            if self.path.exists():
                self._commands = self._load()
                self.path.chmod(0o600)
            else:
                self._commands = list(_DEFAULT_COMMANDS)
                self._save(self._commands)
        except OSError as exc:
            raise BlocklistError(f"Could not initialize command blocklist: {exc}") from exc

    def is_blocked(self, command: str) -> bool:
        """Return whether the command exactly matches a rule or its prefix."""
        return self.blocked_by(command) is not None

    def blocked_by(self, command: str) -> str | None:
        """Return the first matching rule, preserving configured rule order."""
        normalized = command.strip()
        for rule in self._commands:
            if rule.endswith("*"):
                if normalized.startswith(rule[:-1]):
                    return rule
            elif normalized == rule:
                return rule
        return None

    def decision(self, command: str) -> BlockDecision:
        """Return the explicit ALLOW/BLOCK outcome for a command."""
        return BlockDecision.BLOCK if self.is_blocked(command) else BlockDecision.ALLOW

    def add(self, command: str) -> bool:
        """Add a unique rule; return False when it already exists."""
        rule = _validate_rule(command)
        if rule in self._commands:
            return False
        updated = [*self._commands, rule]
        self._save(updated)
        self._commands = updated
        return True

    def remove(self, command: str) -> bool:
        """Remove a rule and return whether it existed."""
        rule = _validate_rule(command)
        if rule not in self._commands:
            return False
        updated = [item for item in self._commands if item != rule]
        self._save(updated)
        self._commands = updated
        return True

    def list_commands(self) -> list[str]:
        """Return a copy of the block rules in configured order."""
        return list(self._commands)

    def _load(self) -> list[str]:
        try:
            with self.path.open(encoding="utf-8") as stream:
                data: Any = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise BlocklistError(f"Could not read command blocklist: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"commands"}:
            raise BlocklistError("Blocklist must contain a 'commands' list.")
        commands = data["commands"]
        if not isinstance(commands, list):
            raise BlocklistError("Blocklist commands must be a list.")
        validated = [_validate_rule(command) for command in commands]
        if len(set(validated)) != len(validated):
            raise BlocklistError("Blocklist contains duplicate rules.")
        return validated

    def _save(self, commands: list[str]) -> None:
        """Atomically replace the JSON file with owner-only permissions."""
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
                json.dump({"commands": commands}, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            self.path.chmod(0o600)
        except OSError as exc:
            raise BlocklistError(f"Could not save command blocklist: {exc}") from exc
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass


def _validate_rule(command: str) -> str:
    """Normalize and validate an exact rule or wildcard-ended prefix rule."""
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Blocklist command must not be empty.")
    rule = command.strip()
    if "*" in rule[:-1]:
        raise ValueError("Wildcard is supported only as the final character.")
    if rule.endswith("*") and not rule[:-1].strip():
        raise ValueError("Prefix blocklist rules must include a command prefix.")
    return rule
