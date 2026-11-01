"""Persistent local execution policy profiles."""

import json
import os
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class ProfileStoreError(RuntimeError):
    """Raised when policy profile storage cannot be read or written safely."""


class ProfileNotFoundError(ProfileStoreError):
    """Raised when a requested policy profile is not configured."""


@dataclass(frozen=True)
class PolicyProfile:
    """Execution constraints for one named environment profile."""

    name: str
    allow_high_risk: bool
    allow_override: bool
    minimum_reputation: int

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Profile name must not be empty.")
        if type(self.allow_high_risk) is not bool or type(self.allow_override) is not bool:
            raise TypeError("Profile allow flags must be booleans.")
        if (
            isinstance(self.minimum_reputation, bool)
            or not isinstance(self.minimum_reputation, int)
            or not 0 <= self.minimum_reputation <= 100
        ):
            raise ValueError("minimum_reputation must be an integer from 0 to 100.")


_DEFAULT_PROFILES = {
    "development": PolicyProfile("development", True, True, 0),
    "staging": PolicyProfile("staging", True, True, 25),
    "production": PolicyProfile("production", False, False, 50),
    "emergency": PolicyProfile("emergency", True, True, 0),
}


class ProfileManager:
    """Load, switch, and persist profiles in a private JSON configuration."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Load the configured profiles or create the documented defaults."""
        self.path = (
            Path(path).expanduser()
            if path is not None
            else Path.home() / ".goyathlay" / "profiles.json"
        )
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise ProfileStoreError("Profile directory and file must not be symbolic links.")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            if self.path.exists():
                self._data = self._load()
                self.path.chmod(0o600)
            else:
                self._data = {
                    "default": "production",
                    "profiles": {
                        name: _profile_values(profile)
                        for name, profile in _DEFAULT_PROFILES.items()
                    },
                }
                self._save(self._data)
        except OSError as exc:
            raise ProfileStoreError(f"Could not initialize policy profiles: {exc}") from exc

    def get_default_profile(self) -> PolicyProfile:
        """Return the profile selected as the default."""
        return self.load_profile(self._data["default"])

    def load_profile(self, name: str) -> PolicyProfile:
        """Load a named profile or raise ProfileNotFoundError."""
        raw = self._data["profiles"].get(name)
        if raw is None:
            raise ProfileNotFoundError(f"Policy profile not found: {name}")
        return PolicyProfile(name=name, **raw)

    def list_profiles(self) -> list[PolicyProfile]:
        """Return configured profiles in stable name order."""
        return [self.load_profile(name) for name in sorted(self._data["profiles"])]

    def save_profile(self, profile: PolicyProfile) -> None:
        """Add or replace a profile without changing the selected default."""
        if not isinstance(profile, PolicyProfile):
            raise TypeError("profile must be a PolicyProfile.")
        updated = deepcopy(self._data)
        updated["profiles"][profile.name] = _profile_values(profile)
        self._commit(updated)

    def set_default_profile(self, name: str) -> None:
        """Persist a new default profile after verifying it exists."""
        self.load_profile(name)
        updated = deepcopy(self._data)
        updated["default"] = name
        self._commit(updated)

    def _commit(self, data: dict[str, Any]) -> None:
        self._save(data)
        self._data = data

    def _load(self) -> dict[str, Any]:
        try:
            with self.path.open(encoding="utf-8") as stream:
                data: Any = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfileStoreError(f"Could not read policy profiles {self.path}: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"default", "profiles"}:
            raise ProfileStoreError("Profile configuration must contain 'default' and 'profiles'.")
        profiles = data["profiles"]
        if not isinstance(data["default"], str) or not isinstance(profiles, dict):
            raise ProfileStoreError("Profile configuration has invalid field types.")
        normalized_profiles: dict[str, dict[str, Any]] = {}
        for name, raw in profiles.items():
            if not isinstance(name, str) or not isinstance(raw, dict):
                raise ProfileStoreError("Profile configuration contains an invalid record.")
            if set(raw) == {"name", "allow_high_risk", "allow_override", "minimum_reputation"}:
                if raw["name"] != name:
                    raise ProfileStoreError(f"Profile record name does not match key {name!r}.")
                raw = {key: value for key, value in raw.items() if key != "name"}
            if set(raw) != {"allow_high_risk", "allow_override", "minimum_reputation"}:
                raise ProfileStoreError(f"Profile record {name!r} has invalid fields.")
            try:
                PolicyProfile(name=name, **raw)
            except (TypeError, ValueError) as exc:
                raise ProfileStoreError(f"Invalid profile {name!r}: {exc}") from exc
            normalized_profiles[name] = raw
        if data["default"] not in profiles:
            raise ProfileNotFoundError(
                f"Default policy profile is not configured: {data['default']}"
            )
        data["profiles"] = normalized_profiles
        return data

    def _save(self, data: dict[str, Any]) -> None:
        """Atomically save config with owner-only permissions."""
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
                json.dump(data, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            self.path.chmod(0o600)
        except OSError as exc:
            raise ProfileStoreError(f"Could not save policy profiles: {exc}") from exc
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass


def _profile_values(profile: PolicyProfile) -> dict[str, object]:
    """Serialize profile settings without duplicating the dictionary key."""
    values = asdict(profile)
    values.pop("name")
    return values
