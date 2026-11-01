"""Local username and password authentication using PBKDF2-HMAC-SHA256."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path

from ..rbac import Role, UserContext


class AuthError(RuntimeError):
    """Raised for invalid local account operations."""


class AuthStoreError(AuthError):
    """Raised when private authentication storage cannot be read or written."""


class AuthManager:
    """Manage local accounts without consulting the operating system or network."""

    ITERATIONS = 310_000

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path else Path.home() / ".goyathlay" / "users.json"
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise AuthStoreError("Authentication storage paths must not be symbolic links.")
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            if self.path.exists():
                self.path.chmod(0o600)
                self._users = self._load()
            else:
                self._users: dict[str, dict[str, str]] = {}
                self._save()
        except OSError as exc:
            raise AuthStoreError(f"Could not initialize local authentication: {exc}") from exc

    def create_user(self, username: str, role: Role, password: str) -> UserContext:
        """Create one user with a salted password hash; never store plaintext."""
        if not isinstance(username, str) or not username.strip() or any(c.isspace() for c in username):
            raise ValueError("username must be non-empty and contain no whitespace.")
        if not isinstance(role, Role):
            raise TypeError("role must be a Role.")
        if not isinstance(password, str) or len(password) < 12:
            raise ValueError("password must contain at least 12 characters.")
        if username in self._users:
            raise AuthError(f"User already exists: {username}")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, self.ITERATIONS)
        self._users[username] = {
            "role": role.name,
            "password_hash": ":".join((
                "pbkdf2_sha256", str(self.ITERATIONS),
                base64.urlsafe_b64encode(salt).decode("ascii"),
                base64.urlsafe_b64encode(digest).decode("ascii"),
            )),
        }
        try:
            self._save()
        except AuthStoreError:
            del self._users[username]
            raise
        return UserContext(username, role)

    def authenticate(self, username: str, password: str) -> UserContext | None:
        """Authenticate locally, returning no details for unknown/bad credentials."""
        record = self._users.get(username)
        if record is None or not isinstance(password, str):
            return None
        try:
            scheme, iterations_text, salt_text, digest_text = record["password_hash"].split(":")
            role = Role[record["role"]]
            if scheme != "pbkdf2_sha256":
                return None
            iterations = int(iterations_text)
            salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        except (KeyError, ValueError, TypeError, UnicodeError):
            return None
        if not hmac.compare_digest(actual, expected):
            return None
        return UserContext(username, role)

    def list_users(self) -> list[UserContext]:
        """Return account names and roles in stable order, never credential data."""
        return [UserContext(name, Role[record["role"]]) for name, record in sorted(self._users.items())]

    def _load(self) -> dict[str, dict[str, str]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthStoreError(f"Could not read local accounts: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"users"} or not isinstance(data["users"], dict):
            raise AuthStoreError("Local account store has an invalid structure.")
        for username, record in data["users"].items():
            if (not isinstance(username, str) or not username or not isinstance(record, dict)
                    or set(record) != {"role", "password_hash"}):
                raise AuthStoreError("Local account store contains an invalid record.")
            try:
                Role[record["role"]]
                parts = record["password_hash"].split(":")
                if len(parts) != 4 or parts[0] != "pbkdf2_sha256" or int(parts[1]) < 100_000:
                    raise ValueError
            except (KeyError, ValueError, TypeError, AttributeError) as exc:
                raise AuthStoreError(f"Invalid credentials record for {username}.") from exc
        return data["users"]

    def _save(self) -> None:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent,
                                             prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as stream:
                temp_path = stream.name
                os.fchmod(stream.fileno(), 0o600)
                json.dump({"users": self._users}, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.path)
            temp_path = None
            self.path.chmod(0o600)
        except OSError as exc:
            raise AuthStoreError(f"Could not save local accounts: {exc}") from exc
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
