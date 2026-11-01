"""Execute validated PostgreSQL queries inside read-only transactions."""

from dataclasses import dataclass
from typing import Any

from .base import DatabaseQuery
from .connection import PostgresConnectionManager
from .profiles import DbProfile
from .validator import QueryValidator


class PostgresExecutionError(RuntimeError):
    """Raised when a PostgreSQL query cannot be validated or executed."""


@dataclass(frozen=True)
class PostgresExecutionResult:
    """Rows and column labels returned from one read-only query."""

    rows: tuple[tuple[Any, ...], ...]
    columns: tuple[str, ...]
    row_count: int


class PostgresExecutor:
    """Execute only validated read-only DatabaseQuery objects."""

    def __init__(self, connection_manager: PostgresConnectionManager,
                 validator: QueryValidator | None = None) -> None:
        """Set the profile connection manager and SQL validator."""
        self.connection_manager = connection_manager
        self.validator = validator or QueryValidator()

    def execute(
        self,
        query: DatabaseQuery,
        profile: DbProfile | str | None = None,
    ) -> PostgresExecutionResult:
        """Execute SQL only after validation, then always roll back and close.

        The transaction is explicitly marked read-only before the query runs.
        Rollback discards transaction state even when execution succeeds.
        """
        if not isinstance(query, DatabaseQuery):
            raise TypeError("query must be a DatabaseQuery.")
        if not query.read_only:
            raise PostgresExecutionError("Only queries marked read-only can be executed.")
        validation = self.validator.validate(query.sql)
        if not validation.allowed:
            raise PostgresExecutionError(f"SQL validation failed: {validation.reason}")

        connection = None
        cursor = None
        try:
            connection = self.connection_manager.connect(profile)
            connection.autocommit = False
            cursor = connection.cursor()
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(query.sql)
            description = cursor.description
            columns = tuple(column.name if hasattr(column, "name") else column[0] for column in description) if description else ()
            rows = tuple(tuple(row) for row in cursor.fetchall()) if description else ()
            return PostgresExecutionResult(rows=rows, columns=columns, row_count=len(rows))
        except PostgresExecutionError:
            raise
        except Exception as exc:
            raise PostgresExecutionError(f"PostgreSQL query execution failed: {exc}") from exc
        finally:
            rollback_error = None
            if connection is not None:
                try:
                    connection.rollback()
                except Exception as exc:
                    rollback_error = exc
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            if rollback_error is not None:
                raise PostgresExecutionError(
                    f"PostgreSQL transaction rollback failed: {rollback_error}"
                ) from rollback_error
