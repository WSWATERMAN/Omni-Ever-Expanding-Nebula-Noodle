"""Persistent local maintenance-window execution controls."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any


class MaintenanceError(RuntimeError):
    """Raised when maintenance-window configuration is invalid or unavailable."""


_DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


@dataclass(frozen=True)
class MaintenanceWindow:
    """A profile-scoped weekly interval expressed in local wall-clock time."""

    name: str
    days: list[str]
    start: str
    end: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Maintenance profile name must not be empty.")
        if not isinstance(self.days, list) or not self.days:
            raise ValueError("Maintenance window requires at least one day.")
        normalized = [day.upper() for day in self.days if isinstance(day, str)]
        if len(normalized) != len(self.days) or any(day not in _DAYS for day in normalized):
            raise ValueError("Days must be weekday abbreviations: MON, TUE, WED, THU, FRI, SAT, SUN.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Maintenance window days must not contain duplicates.")
        object.__setattr__(self, "days", normalized)
        _parse_time(self.start)
        _parse_time(self.end)
        if self.start == self.end:
            raise ValueError("Maintenance window start and end must differ.")


class MaintenanceManager:
    """Manage profile-specific maintenance windows in a private JSON file."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Load existing settings or create the disabled default configuration."""
        self.path = Path(path).expanduser() if path is not None else Path.home() / ".goyathlay" / "maintenance.json"
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise MaintenanceError("Maintenance directory and file must not be symbolic links.")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            if self.path.exists():
                self._data = self._load()
                self.path.chmod(0o600)
            else:
                self._data = {"enabled": False, "windows": []}
                self._save(self._data)
        except OSError as exc:
            raise MaintenanceError(f"Could not initialize maintenance settings: {exc}") from exc

    @property
    def enabled(self) -> bool:
        """Return whether configured windows are enforced."""
        return self._data["enabled"]

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable maintenance-window enforcement and persist it."""
        if type(enabled) is not bool:
            raise TypeError("enabled must be a bool.")
        updated = {"enabled": enabled, "windows": list(self._data["windows"])}
        self._commit(updated)

    def is_allowed(self, profile_name: str, now: datetime) -> bool:
        """Return whether this profile is permitted at the supplied local time.

        With enforcement disabled or no windows configured, access is allowed.
        An overnight interval is attributed to the day on which it starts.
        """
        if not self.enabled or not self._data["windows"]:
            return True
        if not isinstance(now, datetime):
            raise TypeError("now must be a datetime.")
        minute = now.hour * 60 + now.minute
        today = _DAYS[now.weekday()]
        yesterday = _DAYS[(now.weekday() - 1) % 7]
        for window in self._data["windows"]:
            if window["name"] != profile_name:
                continue
            start = _minute(window["start"])
            end = _minute(window["end"])
            if start < end and today in window["days"] and start <= minute < end:
                return True
            if start > end:
                if today in window["days"] and minute >= start:
                    return True
                if yesterday in window["days"] and minute < end:
                    return True
            if start == end and today in window["days"] and minute == start:
                return True
        return False

    def list_windows(self) -> list[MaintenanceWindow]:
        """Return configured windows in insertion order."""
        return [MaintenanceWindow(**{**item, "days": list(item["days"])}) for item in self._data["windows"]]

    def add_window(self, window: MaintenanceWindow | str, days: list[str] | None = None,
                   start: str | None = None, end: str | None = None) -> bool:
        """Add a unique window; accepts either a record or its four fields."""
        if isinstance(window, MaintenanceWindow):
            record = window
        else:
            if days is None or start is None or end is None:
                raise TypeError("add_window requires a window or name, days, start, and end.")
            record = MaintenanceWindow(window, days, start, end)
        item = asdict(record)
        if item in self._data["windows"]:
            return False
        self._commit({"enabled": self.enabled, "windows": [*self._data["windows"], item]})
        return True

    def remove_window(self, name: str) -> bool:
        """Remove all windows for a profile name, returning whether any existed."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Maintenance profile name must not be empty.")
        windows = [item for item in self._data["windows"] if item["name"] != name]
        if len(windows) == len(self._data["windows"]):
            return False
        self._commit({"enabled": self.enabled, "windows": windows})
        return True

    def _load(self) -> dict[str, Any]:
        try:
            with self.path.open(encoding="utf-8") as stream:
                raw: Any = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise MaintenanceError(f"Could not read maintenance settings: {exc}") from exc
        if not isinstance(raw, dict) or set(raw) != {"enabled", "windows"}:
            raise MaintenanceError("Maintenance settings must contain 'enabled' and 'windows'.")
        if type(raw["enabled"]) is not bool or not isinstance(raw["windows"], list):
            raise MaintenanceError("Maintenance settings have invalid field types.")
        validated = []
        try:
            for item in raw["windows"]:
                if not isinstance(item, dict) or set(item) != {"name", "days", "start", "end"}:
                    raise ValueError("Window records must contain name, days, start, and end.")
                validated.append(asdict(MaintenanceWindow(**item)))
        except (TypeError, ValueError) as exc:
            raise MaintenanceError(f"Invalid maintenance window: {exc}") from exc
        raw["windows"] = validated
        return raw

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
                json.dump(data, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            self.path.chmod(0o600)
        except OSError as exc:
            raise MaintenanceError(f"Could not save maintenance settings: {exc}") from exc
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass


def _parse_time(value: str) -> time:
    """Parse a strict 24-hour HH:MM value."""
    if not isinstance(value, str):
        raise ValueError("Window times must use HH:MM format.")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Window times must use HH:MM format.") from exc
    if parsed.second or parsed.microsecond or len(value) != 5:
        raise ValueError("Window times must use HH:MM format.")
    return parsed


def _minute(value: str) -> int:
    parsed = _parse_time(value)
    return parsed.hour * 60 + parsed.minute
