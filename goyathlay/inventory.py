"""Private, persistent inventory of named SSH hosts and host groups."""

import json
import os
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class InventoryError(RuntimeError):
    """Raised when the host inventory is invalid or cannot be safely stored."""


@dataclass(frozen=True)
class HostRecord:
    """Connection information for one named SSH host."""

    name: str
    hostname: str
    port: int
    username: str

    def __post_init__(self) -> None:
        for field_name in ("name", "hostname", "username"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty.")
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("port must be an integer between 1 and 65535.")


class HostInventory:
    """Manage named SSH hosts and groups in an owner-only JSON file."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Load the inventory, creating an empty one when it does not exist."""
        self.path = (
            Path(path).expanduser()
            if path is not None
            else Path.home() / ".goyathlay" / "inventory.json"
        )
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise InventoryError("Inventory directory and file must not be symbolic links.")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            if self.path.exists():
                self._data = self._load()
                self.path.chmod(0o600)
            else:
                self._data: dict[str, Any] = {"hosts": {}, "groups": {}}
                self._save(self._data)
        except OSError as exc:
            raise InventoryError(f"Could not initialize host inventory: {exc}") from exc

    def add_host(self, host: HostRecord) -> None:
        """Add a unique host record and persist it."""
        if not isinstance(host, HostRecord):
            raise TypeError("host must be a HostRecord.")
        if host.name in self._data["hosts"] or host.name in self._data["groups"]:
            raise InventoryError(f"Target name already exists: {host.name}")
        updated = deepcopy(self._data)
        updated["hosts"][host.name] = asdict(host)
        self._commit(updated)

    def remove_host(self, name: str) -> bool:
        """Remove a host and its memberships in all groups, if present."""
        if name not in self._data["hosts"]:
            return False
        updated = deepcopy(self._data)
        del updated["hosts"][name]
        for members in updated["groups"].values():
            members[:] = [member for member in members if member != name]
        self._commit(updated)
        return True

    def get_host(self, name: str) -> HostRecord | None:
        """Return a named host record, or None when it is not present."""
        raw = self._data["hosts"].get(name)
        return HostRecord(**raw) if raw is not None else None

    def list_hosts(self) -> list[HostRecord]:
        """Return host records in stable name order."""
        return [self.get_host(name) for name in sorted(self._data["hosts"])]  # type: ignore[list-item]

    def add_group(self, name: str, members: list[str]) -> None:
        """Add a unique group whose members all refer to configured hosts."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Group name must not be empty.")
        if name in self._data["groups"] or name in self._data["hosts"]:
            raise InventoryError(f"Target name already exists: {name}")
        if not isinstance(members, list) or any(not isinstance(item, str) for item in members):
            raise TypeError("members must be a list of host names.")
        if len(set(members)) != len(members):
            raise InventoryError("Group members must not contain duplicates.")
        missing = [member for member in members if member not in self._data["hosts"]]
        if missing:
            raise InventoryError(f"Unknown host(s) in group {name!r}: {', '.join(missing)}")
        updated = deepcopy(self._data)
        updated["groups"][name] = list(members)
        self._commit(updated)

    def remove_group(self, name: str) -> bool:
        """Remove a group and return whether it existed."""
        if name not in self._data["groups"]:
            return False
        updated = deepcopy(self._data)
        del updated["groups"][name]
        self._commit(updated)
        return True

    def get_group(self, name: str) -> list[str] | None:
        """Return a copy of a group's host names, or None when absent."""
        members = self._data["groups"].get(name)
        return list(members) if members is not None else None

    def list_groups(self) -> dict[str, list[str]]:
        """Return a copy of all groups and their host names."""
        return {name: list(members) for name, members in sorted(self._data["groups"].items())}

    def resolve_target(self, name: str) -> list[HostRecord]:
        """Resolve a host or group name to its configured host records."""
        host = self.get_host(name)
        if host is not None:
            return [host]
        members = self.get_group(name)
        if members is None:
            raise InventoryError(f"Unknown host or group: {name}")
        return [self.get_host(member) for member in members]  # type: ignore[list-item]

    def _commit(self, data: dict[str, Any]) -> None:
        self._save(data)
        self._data = data

    def _load(self) -> dict[str, Any]:
        try:
            with self.path.open(encoding="utf-8") as stream:
                data: Any = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise InventoryError(f"Could not read inventory {self.path}: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"hosts", "groups"}:
            raise InventoryError("Inventory must contain 'hosts' and 'groups' objects.")
        hosts, groups = data["hosts"], data["groups"]
        if not isinstance(hosts, dict) or not isinstance(groups, dict):
            raise InventoryError("Inventory hosts and groups must be objects.")
        for name, raw in hosts.items():
            if not isinstance(name, str) or not isinstance(raw, dict):
                raise InventoryError("Inventory contains an invalid host record.")
            if set(raw) != {"name", "hostname", "port", "username"} or raw["name"] != name:
                raise InventoryError(f"Invalid host record for {name!r}.")
            try:
                HostRecord(**raw)
            except (TypeError, ValueError) as exc:
                raise InventoryError(f"Invalid host record for {name!r}: {exc}") from exc
        if set(hosts).intersection(groups):
            raise InventoryError("Host and group names must be unique across the inventory.")
        for name, members in groups.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(members, list):
                raise InventoryError("Inventory contains an invalid group record.")
            if any(not isinstance(member, str) or member not in hosts for member in members):
                raise InventoryError(f"Group {name!r} contains an unknown host reference.")
            if len(set(members)) != len(members):
                raise InventoryError(f"Group {name!r} contains duplicate host references.")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        """Atomically persist inventory with owner-only file permissions."""
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
            raise InventoryError(f"Could not save host inventory: {exc}") from exc
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
