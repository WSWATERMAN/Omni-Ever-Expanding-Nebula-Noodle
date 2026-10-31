"""Private, atomic JSON storage for trusted SSH host fingerprints."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .host_identity import HostIdentity


class TrustStoreError(RuntimeError):
    """Raised when the trust database cannot be read or safely written."""


class TrustStore:
    """Load and persist trusted SSH identities in a private JSON file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else Path.home() / ".goyathlay" / "trust_store.json"
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise TrustStoreError("Trust store directory and file must not be symbolic links.")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
        except OSError as exc:
            raise TrustStoreError(f"Could not secure trust store directory: {exc}") from exc

        if self.path.exists():
            self._data = self._read()
            try:
                self.path.chmod(0o600)
            except OSError as exc:
                raise TrustStoreError(f"Could not secure trust store file: {exc}") from exc
        else:
            self._data: dict[str, dict[str, dict[str, str]]] = {"hosts": {}}
            self.save()

    @staticmethod
    def host_key(host: str, port: int) -> str:
        """Return an unambiguous trust key, separating nonstandard ports."""
        if port == 22:
            return host
        if ":" in host and not host.startswith("["):
            return f"[{host}]:{port}"
        return f"{host}:{port}"

    def lookup(self, host: str, port: int = 22) -> dict[str, str] | None:
        """Return a copy of a saved host record, if present."""
        record = self._data["hosts"].get(self.host_key(host, port))
        return dict(record) if record is not None else None

    def store(self, identity: HostIdentity) -> None:
        """Persist the identity, retaining the original first-seen timestamp."""
        key = self.host_key(identity.host, identity.port)
        now = _utc_now()
        existing = self._data["hosts"].get(key)
        self._data["hosts"][key] = {
            "fingerprint": identity.fingerprint,
            "algorithm": identity.algorithm,
            "first_seen": existing["first_seen"] if existing else now,
            "last_verified": now,
        }
        self.save()

    def mark_verified(self, host: str, port: int = 22) -> None:
        """Update the last-verified timestamp of an existing trusted host."""
        record = self._data["hosts"].get(self.host_key(host, port))
        if record is None:
            raise TrustStoreError("Cannot verify a host that is not trusted.")
        record["last_verified"] = _utc_now()
        self.save()

    def remove(self, host: str, port: int = 22) -> bool:
        """Remove a trusted host and return whether a record existed."""
        key = self.host_key(host, port)
        if key not in self._data["hosts"]:
            return False
        del self._data["hosts"][key]
        self.save()
        return True

    def save(self) -> None:
        """Atomically write the trust database with owner-only permissions."""
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
                json.dump(self._data, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            self.path.chmod(0o600)
        except OSError as exc:
            raise TrustStoreError(f"Could not save trust store: {exc}") from exc
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

    def _read(self) -> dict[str, dict[str, dict[str, str]]]:
        try:
            with self.path.open(encoding="utf-8") as stream:
                data: Any = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise TrustStoreError(f"Could not read trust store {self.path}: {exc}") from exc

        if not isinstance(data, dict) or not isinstance(data.get("hosts"), dict):
            raise TrustStoreError("Trust store must contain a 'hosts' object.")
        for host, record in data["hosts"].items():
            if not isinstance(host, str) or not isinstance(record, dict):
                raise TrustStoreError("Trust store contains an invalid host record.")
            required = {"fingerprint", "algorithm", "first_seen", "last_verified"}
            if not required.issubset(record) or not all(isinstance(record[key], str) for key in required):
                raise TrustStoreError(f"Trust store record for {host!r} is incomplete.")
        return data


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
