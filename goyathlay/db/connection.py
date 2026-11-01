"""Lazy psycopg3 connection setup backed by local PostgreSQL profiles."""

from pathlib import Path
from typing import Any

from .profiles import DbProfile, DbProfileStore


class DatabaseConnectionError(RuntimeError):
    """Raised when psycopg is unavailable or a PostgreSQL connection fails."""


class PostgresConnectionManager:
    """Load local connection profiles and open PostgreSQL connections."""

    def __init__(self, path: str | Path | None = None, *, psycopg_module: Any | None = None,
                 profile_store: DbProfileStore | None = None, connect_timeout: int = 5) -> None:
        """Initialize local profile storage without importing psycopg yet."""
        if path is not None and profile_store is not None:
            raise ValueError("Pass path or profile_store, not both.")
        if connect_timeout < 1:
            raise ValueError("connect_timeout must be positive.")
        self.profile_store = profile_store if profile_store is not None else DbProfileStore(path)
        self._psycopg = psycopg_module
        self.connect_timeout = connect_timeout

    def load_profile(self, name: str | None = None) -> DbProfile:
        """Load a named profile or the configured default."""
        return self.profile_store.load_profile(name)

    def list_profiles(self) -> list[DbProfile]:
        """Return all configured PostgreSQL profiles."""
        return self.profile_store.list_profiles()

    def set_default_profile(self, name: str) -> None:
        """Persist the default profile selection."""
        self.profile_store.set_default_profile(name)

    def add_profile(self, profile: DbProfile, *, make_default: bool = False) -> None:
        """Persist connection coordinates, optionally selecting them by default."""
        self.profile_store.add_profile(profile, make_default=make_default)

    def connect(self, profile: DbProfile | str | None = None) -> Any:
        """Open a connection with read-only defaults and autocommit disabled.

        Passwords are intentionally not stored in profile JSON. psycopg/libpq
        may obtain credentials from standard mechanisms such as ``.pgpass``.
        """
        selected = self.load_profile(profile) if isinstance(profile, str) or profile is None else profile
        if not isinstance(selected, DbProfile):
            raise TypeError("profile must be a DbProfile, profile name, or None.")
        psycopg = self._get_psycopg()
        connection = None
        try:
            connection = psycopg.connect(
                host=selected.host,
                port=selected.port,
                dbname=selected.database,
                user=selected.username,
                connect_timeout=self.connect_timeout,
                application_name="goyathlay",
                options="-c default_transaction_read_only=on",
            )
            connection.autocommit = False
            return connection
        except Exception as exc:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            raise DatabaseConnectionError(
                f"Could not connect to PostgreSQL profile {selected.name!r} "
                f"at {selected.host}:{selected.port}/{selected.database}: {exc}"
            ) from exc

    def _get_psycopg(self) -> Any:
        if self._psycopg is None:
            try:
                import psycopg  # type: ignore[import-not-found]
            except ImportError as exc:
                raise DatabaseConnectionError(
                    "PostgreSQL support requires psycopg 3; install it with 'pip install psycopg[binary]'."
                ) from exc
            self._psycopg = psycopg
        return self._psycopg
