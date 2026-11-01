"""Execute validated SQLite statements against database files in read-only mode."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .sqlite_profiles import SqliteProfile
from .validator import QueryValidator


class SqliteExecutionError(RuntimeError):
    """Raised when a SQLite query is invalid or cannot be executed safely."""


@dataclass(frozen=True)
class QueryResult:
    """Column labels, fetched rows, and row count for a SQLite query."""

    columns: list[str]
    rows: list[tuple[Any, ...]]
    row_count: int


class SqliteExecutor:
    """Validate and execute one SQL statement against a read-only DB handle."""

    def __init__(self, validator: QueryValidator | None = None) -> None:
        """Configure SQL validation; no database handle is opened yet."""
        self.validator = validator or QueryValidator()

    def execute(self, profile: SqliteProfile, sql: str) -> QueryResult:
        """Run SQL using SQLite URI ``mode=ro`` and a deny-by-default authorizer."""
        if not isinstance(profile, SqliteProfile):
            raise TypeError("profile must be a SqliteProfile.")
        validation = self.validator.validate(sql)
        if not validation.allowed:
            raise SqliteExecutionError(f"SQL validation failed: {validation.reason}")

        database_uri = Path(profile.database).expanduser().resolve().as_uri() + "?mode=ro"
        connection = None
        cursor = None
        try:
            connection = sqlite3.connect(database_uri, uri=True)
            connection.set_authorizer(_read_only_authorizer)
            cursor = connection.execute(sql)
            columns = [description[0] for description in cursor.description or ()]
            rows = [tuple(row) for row in cursor.fetchall()] if cursor.description else []
            return QueryResult(columns=columns, rows=rows, row_count=len(rows))
        except sqlite3.Error as exc:
            raise SqliteExecutionError(f"SQLite query execution failed: {exc}") from exc
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except sqlite3.Error:
                    pass
            if connection is not None:
                connection.close()


def _read_only_authorizer(action: int, arg1: str | None, arg2: str | None,
                          database: str | None, source: str | None) -> int:
    """Allow only query/read/function authorizer events; deny writes and pragmas."""
    del database, source
    allowed_actions = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
    }
    recursive = getattr(sqlite3, "SQLITE_RECURSIVE", None)
    if recursive is not None:
        allowed_actions.add(recursive)
    if action == sqlite3.SQLITE_PRAGMA:
        # SQLite implements table-valued read-only PRAGMAs as authorizer
        # PRAGMA events. Permit only table-valued read APIs used by inspection
        # queries; direct PRAGMA statements are denied by SQL validation.
        pragma = arg1.casefold() if arg1 is not None else ""
        if pragma in {"page_count", "page_size"} and arg2 is None:
            return sqlite3.SQLITE_OK
        if pragma == "foreign_key_list" and isinstance(arg2, str) and arg2:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK if action in allowed_actions else sqlite3.SQLITE_DENY
