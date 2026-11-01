"""Execute validated SQL Server queries with pyodbc and rollback."""

import os
from dataclasses import dataclass
from typing import Any

from .base import DatabaseQuery
from .mssql_profiles import MssqlProfile, MssqlProfileManager
from .validator import QueryValidator


class MssqlExecutionError(RuntimeError):
    """Raised when SQL Server access or query execution fails."""


@dataclass(frozen=True)
class MssqlQueryResult:
    """Fetched rows, column labels, and row count for a SQL Server query."""

    columns: list[str]
    rows: list[tuple[Any, ...]]
    row_count: int


class MssqlExecutor:
    """Execute a validated SELECT query using a least-privilege ODBC profile."""

    def __init__(self, profiles: MssqlProfileManager, *, pyodbc_module: Any | None = None,
                 validator: QueryValidator | None = None) -> None:
        self.profiles = profiles
        self._pyodbc = pyodbc_module
        self.validator = validator or QueryValidator()

    def execute(self, profile: MssqlProfile | str | None, sql: str) -> MssqlQueryResult:
        """Validate, execute, fetch, roll back, and close one SQL statement."""
        selected = self.profiles.load_profile(profile) if isinstance(profile, str) or profile is None else profile
        if not isinstance(selected, MssqlProfile):
            raise TypeError("profile must be an MssqlProfile, profile name, or None.")
        validation = self.validator.validate(sql)
        if not validation.allowed:
            raise MssqlExecutionError(f"SQL validation failed: {validation.reason}")
        if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
            raise MssqlExecutionError("Only SELECT and WITH queries are supported by MSSQL execution.")
        pyodbc = self._get_pyodbc()
        secret = os.environ.get("GOYATHLAY_MSSQL_PASSWORD")
        if not secret:
            raise MssqlExecutionError("Set GOYATHLAY_MSSQL_PASSWORD or configure an approved ODBC credential source.")
        connection_string = (
            f"DRIVER={{{selected.driver}}};SERVER=tcp:{selected.server},{selected.port};"
            f"DATABASE={selected.database};UID={selected.username};PWD={_odbc_value(secret)};"
            "Encrypt=yes;TrustServerCertificate=no;ApplicationIntent=ReadOnly;"
        )
        connection = None
        cursor = None
        try:
            connection = pyodbc.connect(connection_string, timeout=5, autocommit=False)
            cursor = connection.cursor()
            cursor.execute(sql)
            columns = [column[0] for column in (cursor.description or ())]
            rows = [tuple(row) for row in cursor.fetchall()] if cursor.description else []
            return MssqlQueryResult(columns, rows, len(rows))
        except Exception as exc:
            raise MssqlExecutionError(f"SQL Server query execution failed: {exc}") from exc
        finally:
            if connection is not None:
                try:
                    connection.rollback()
                except Exception:
                    pass
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                try:
                    connection.close()
                except Exception:
                    pass

    def _get_pyodbc(self) -> Any:
        if self._pyodbc is None:
            try:
                import pyodbc  # type: ignore[import-not-found]
            except ImportError as exc:
                raise MssqlExecutionError("MSSQL support requires pyodbc; install it with 'pip install pyodbc'.") from exc
            self._pyodbc = pyodbc
        return self._pyodbc


def _odbc_value(value: str) -> str:
    """Quote an ODBC connection-string value without interpolation escapes."""
    return "{" + value.replace("}", "}}") + "}"
