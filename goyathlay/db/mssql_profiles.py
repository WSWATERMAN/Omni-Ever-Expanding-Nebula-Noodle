"""Private JSON connection profiles for Microsoft SQL Server."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MssqlProfileError(RuntimeError):
    """Raised for invalid or unavailable SQL Server profile storage."""


class MssqlProfileNotFoundError(MssqlProfileError):
    """Raised when a named or default SQL Server profile is not configured."""


@dataclass(frozen=True)
class MssqlProfile:
    """SQL Server endpoint and login name; passwords are never persisted."""

    name: str
    server: str
    database: str
    username: str
    port: int = 1433
    driver: str = "ODBC Driver 18 for SQL Server"

    def __post_init__(self) -> None:
        for field in ("name", "server", "database", "username", "driver"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must not be empty.")
            if any(character in value for character in ";{}\x00"):
                raise ValueError(f"{field} contains unsupported ODBC connection-string characters.")
        if "," in self.server:
            raise ValueError("server must not contain a comma because ODBC uses commas to delimit ports.")
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535.")


class MssqlProfileManager:
    """Manage private SQL Server connection profiles."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Load existing profiles or create an empty private configuration."""
        self.path = Path(path).expanduser() if path else Path.home() / ".goyathlay" / "mssql_profiles.json"
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise MssqlProfileError("SQL Server profile path must not be a symbolic link.")
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
            raise MssqlProfileError(f"Could not initialize SQL Server profiles: {exc}") from exc

    def add_profile(self, profile: MssqlProfile, *, make_default: bool = False) -> None:
        """Add or replace a profile without persisting credentials."""
        if not isinstance(profile, MssqlProfile):
            raise TypeError("profile must be an MssqlProfile.")
        profiles = dict(self._data["profiles"])
        profiles[profile.name] = _profile_record(profile)
        default = profile.name if make_default or self._data["default"] is None else self._data["default"]
        self._commit({"default": default, "profiles": profiles})

    def remove_profile(self, name: str) -> bool:
        """Remove a profile and clear the default if necessary."""
        if name not in self._data["profiles"]:
            return False
        profiles = dict(self._data["profiles"])
        del profiles[name]
        default = None if self._data["default"] == name else self._data["default"]
        self._commit({"default": default, "profiles": profiles})
        return True

    def load_profile(self, name: str | None = None) -> MssqlProfile:
        """Load a named profile or the configured default."""
        name = name if name is not None else self._data["default"]
        raw = self._data["profiles"].get(name) if name is not None else None
        if raw is None:
            raise MssqlProfileNotFoundError(f"SQL Server profile not found: {name or '(default)'}")
        return MssqlProfile(name=name, **raw)

    def list_profiles(self) -> list[MssqlProfile]:
        """Return profiles in stable name order."""
        return [self.load_profile(name) for name in sorted(self._data["profiles"])]

    def set_default_profile(self, name: str) -> None:
        """Select a configured profile as the default."""
        self.load_profile(name)
        self._commit({"default": name, "profiles": dict(self._data["profiles"])})

    def get_default_profile(self) -> MssqlProfile:
        """Return the selected profile."""
        return self.load_profile()

    @property
    def default_name(self) -> str | None:
        """Return the selected profile name."""
        return self._data["default"]

    def _load(self) -> dict[str, Any]:
        try:
            with self.path.open(encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise MssqlProfileError(f"Could not read SQL Server profiles: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"default", "profiles"}:
            raise MssqlProfileError("SQL Server profiles must contain default and profiles fields.")
        if data["default"] is not None and not isinstance(data["default"], str):
            raise MssqlProfileError("Default profile must be a string or null.")
        if not isinstance(data["profiles"], dict):
            raise MssqlProfileError("Profiles must be an object.")
        profiles = {}
        for name, raw in data["profiles"].items():
            if not isinstance(name, str) or not isinstance(raw, dict):
                raise MssqlProfileError("Invalid SQL Server profile record.")
            if set(raw) == {"server", "database", "username", "port"}:
                raw = {**raw, "driver": "ODBC Driver 18 for SQL Server"}
            if set(raw) != {"server", "database", "username", "port", "driver"}:
                raise MssqlProfileError(f"Invalid SQL Server profile fields: {name}")
            try:
                MssqlProfile(name=name, **raw)
            except (TypeError, ValueError) as exc:
                raise MssqlProfileError(f"Invalid SQL Server profile {name}: {exc}") from exc
            profiles[name] = raw
        if data["default"] is not None and data["default"] not in profiles:
            raise MssqlProfileNotFoundError(f"Default SQL Server profile not found: {data['default']}")
        return {"default": data["default"], "profiles": profiles}

    def _commit(self, data: dict[str, Any]) -> None:
        self._save(data)
        self._data = data

    def _save(self, data: dict[str, Any]) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent,
                                             prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                os.fchmod(stream.fileno(), 0o600)
                json.dump(data, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            self.path.chmod(0o600)
        except OSError as exc:
            raise MssqlProfileError(f"Could not save SQL Server profiles: {exc}") from exc
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass


def _profile_record(profile: MssqlProfile) -> dict[str, object]:
    return {"server": profile.server, "port": profile.port, "database": profile.database,
            "username": profile.username, "driver": profile.driver}
