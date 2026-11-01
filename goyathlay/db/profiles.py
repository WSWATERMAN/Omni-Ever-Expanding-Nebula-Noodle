"""Private JSON storage for PostgreSQL connection profiles."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class DatabaseProfileError(RuntimeError):
    """Raised when database profile storage cannot be loaded or saved."""


class DatabaseProfileNotFoundError(DatabaseProfileError):
    """Raised when a named or default database profile does not exist."""


@dataclass(frozen=True)
class DbProfile:
    """Connection coordinates for a PostgreSQL database, without a password."""

    name: str
    host: str
    port: int
    database: str
    username: str

    def __post_init__(self) -> None:
        for field in ("name", "host", "database", "username"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Database profile {field} must not be empty.")
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("Database profile port must be an integer from 1 to 65535.")


class DbProfileStore:
    """Persist database profiles with atomic writes and owner-only permissions."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Load profiles or create an empty configuration ready for enrollment."""
        self.path = Path(path).expanduser() if path is not None else Path.home() / ".goyathlay" / "db_profiles.json"
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise DatabaseProfileError("Database profile directory and file must not be symbolic links.")
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
            raise DatabaseProfileError(f"Could not initialize database profiles: {exc}") from exc

    def load_profile(self, name: str | None = None) -> DbProfile:
        """Load a named profile or the selected default profile."""
        selected = name if name is not None else self._data["default"]
        if selected is None:
            raise DatabaseProfileNotFoundError("No default database profile is configured.")
        raw = self._data["profiles"].get(selected)
        if raw is None:
            raise DatabaseProfileNotFoundError(f"Database profile not found: {selected}")
        return DbProfile(name=selected, **raw)

    def list_profiles(self) -> list[DbProfile]:
        """Return configured profiles sorted by name."""
        return [self.load_profile(name) for name in sorted(self._data["profiles"])]

    def add_profile(self, profile: DbProfile, *, make_default: bool = False) -> None:
        """Add or replace profile coordinates and optionally select the default."""
        if not isinstance(profile, DbProfile):
            raise TypeError("profile must be a DbProfile.")
        data = {"default": self._data["default"], "profiles": dict(self._data["profiles"])}
        values = asdict(profile)
        values.pop("name")
        data["profiles"][profile.name] = values
        if make_default or data["default"] is None:
            data["default"] = profile.name
        self._commit(data)

    def set_default_profile(self, name: str) -> None:
        """Select an existing profile as the default."""
        self.load_profile(name)
        data = {"default": name, "profiles": dict(self._data["profiles"])}
        self._commit(data)

    @property
    def default_name(self) -> str | None:
        """Return the selected profile name, if set."""
        return self._data["default"]

    def _load(self) -> dict[str, Any]:
        try:
            with self.path.open(encoding="utf-8") as stream:
                data: Any = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise DatabaseProfileError(f"Could not read database profiles: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"default", "profiles"}:
            raise DatabaseProfileError("Database profile file must contain 'default' and 'profiles'.")
        if data["default"] is not None and not isinstance(data["default"], str):
            raise DatabaseProfileError("Default database profile must be a string or null.")
        if not isinstance(data["profiles"], dict):
            raise DatabaseProfileError("Database profiles must be an object.")
        profiles: dict[str, dict[str, Any]] = {}
        for name, raw in data["profiles"].items():
            if not isinstance(name, str) or not isinstance(raw, dict) or set(raw) != {
                "host", "port", "database", "username"
            }:
                raise DatabaseProfileError(f"Invalid database profile record: {name!r}.")
            try:
                DbProfile(name=name, **raw)
            except (TypeError, ValueError) as exc:
                raise DatabaseProfileError(f"Invalid database profile {name!r}: {exc}") from exc
            profiles[name] = raw
        if data["default"] is not None and data["default"] not in profiles:
            raise DatabaseProfileNotFoundError(f"Default database profile not found: {data['default']}")
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
            raise DatabaseProfileError(f"Could not save database profiles: {exc}") from exc
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
