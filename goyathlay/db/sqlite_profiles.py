"""Private, atomic storage for SQLite database file profiles."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SqliteProfileError(RuntimeError):
    """Raised when SQLite profiles cannot be read or written safely."""


class SqliteProfileNotFoundError(SqliteProfileError):
    """Raised when a requested SQLite profile is not configured."""


@dataclass(frozen=True)
class SqliteProfile:
    """A named SQLite database file location."""

    name: str
    database: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("SQLite profile name must not be empty.")
        if not isinstance(self.database, str) or not self.database.strip():
            raise ValueError("SQLite database path must not be empty.")


class SqliteProfileManager:
    """Add, select, remove, and list profiles in a private JSON document."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Load configured profiles or create an empty profile document."""
        self.path = Path(path).expanduser() if path is not None else Path.home() / ".goyathlay" / "sqlite_profiles.json"
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise SqliteProfileError("SQLite profile directory and file must not be symbolic links.")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            if self.path.exists():
                self._data = self._load()
                self.path.chmod(0o600)
            else:
                self._data = {"default": None, "profiles": {}}
                self._save(self._data)
        except OSError as exc:
            raise SqliteProfileError(f"Could not initialize SQLite profiles: {exc}") from exc

    def add_profile(self, profile: SqliteProfile, *, make_default: bool = False) -> None:
        """Add or update a profile, selecting it when requested or no default exists."""
        if not isinstance(profile, SqliteProfile):
            raise TypeError("profile must be a SqliteProfile.")
        data = {"default": self._data["default"], "profiles": dict(self._data["profiles"])}
        data["profiles"][profile.name] = {"database": profile.database}
        if make_default or data["default"] is None:
            data["default"] = profile.name
        self._commit(data)

    def remove_profile(self, name: str) -> bool:
        """Remove a profile, clearing the default when it referred to that name."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("SQLite profile name must not be empty.")
        if name not in self._data["profiles"]:
            return False
        profiles = dict(self._data["profiles"])
        del profiles[name]
        default = None if self._data["default"] == name else self._data["default"]
        self._commit({"default": default, "profiles": profiles})
        return True

    def load_profile(self, name: str) -> SqliteProfile:
        """Load a named profile or raise SqliteProfileNotFoundError."""
        raw = self._data["profiles"].get(name)
        if raw is None:
            raise SqliteProfileNotFoundError(f"SQLite profile not found: {name}")
        return SqliteProfile(name=name, **raw)

    def list_profiles(self) -> list[SqliteProfile]:
        """Return configured profiles in stable name order."""
        return [self.load_profile(name) for name in sorted(self._data["profiles"])]

    def set_default_profile(self, name: str) -> None:
        """Persist the selected default profile after verifying it exists."""
        self.load_profile(name)
        self._commit({"default": name, "profiles": dict(self._data["profiles"])})

    def get_default_profile(self) -> SqliteProfile:
        """Return the selected profile or raise when none is configured."""
        name = self._data["default"]
        if name is None:
            raise SqliteProfileNotFoundError("No default SQLite profile is configured.")
        return self.load_profile(name)

    @property
    def default_name(self) -> str | None:
        """Return the configured default profile name."""
        return self._data["default"]

    def _load(self) -> dict[str, Any]:
        try:
            with self.path.open(encoding="utf-8") as stream:
                data: Any = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise SqliteProfileError(f"Could not load SQLite profiles: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"default", "profiles"}:
            raise SqliteProfileError("SQLite profiles must contain 'default' and 'profiles'.")
        if data["default"] is not None and not isinstance(data["default"], str):
            raise SqliteProfileError("Default SQLite profile must be a string or null.")
        if not isinstance(data["profiles"], dict):
            raise SqliteProfileError("SQLite profiles must be an object.")
        profiles: dict[str, dict[str, str]] = {}
        for name, raw in data["profiles"].items():
            if not isinstance(name, str) or not isinstance(raw, dict) or set(raw) != {"database"}:
                raise SqliteProfileError(f"Invalid SQLite profile record: {name!r}.")
            try:
                SqliteProfile(name, raw["database"])
            except (TypeError, ValueError) as exc:
                raise SqliteProfileError(f"Invalid SQLite profile {name!r}: {exc}") from exc
            profiles[name] = raw
        if data["default"] is not None and data["default"] not in profiles:
            raise SqliteProfileNotFoundError(f"Default SQLite profile not found: {data['default']}")
        return {"default": data["default"], "profiles": profiles}

    def _commit(self, data: dict[str, Any]) -> None:
        self._save(data)
        self._data = data

    def _save(self, data: dict[str, Any]) -> None:
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as stream:
                temporary_path = stream.name
                os.fchmod(stream.fileno(), 0o600)
                json.dump(data, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            self.path.chmod(0o600)
        except OSError as exc:
            raise SqliteProfileError(f"Could not save SQLite profiles: {exc}") from exc
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
