"""Database intent translation and SQL validation primitives."""

from .base import DatabaseInterpreter, DatabaseQuery, UnsupportedIntentError
from .connection import DatabaseConnectionError, PostgresConnectionManager
from .executor import PostgresExecutionError, PostgresExecutionResult, PostgresExecutor
from .postgres import PostgresInterpreter
from .profiles import (
    DatabaseProfileError,
    DatabaseProfileNotFoundError,
    DbProfile,
    DbProfileStore,
)
from .sqlite import SqliteInterpreter
from .sqlite_executor import QueryResult, SqliteExecutionError, SqliteExecutor
from .sqlite_profiles import (
    SqliteProfile,
    SqliteProfileError,
    SqliteProfileManager,
    SqliteProfileNotFoundError,
)
from .mssql import MssqlInterpreter
from .mssql_executor import MssqlExecutionError, MssqlExecutor, MssqlQueryResult
from .mssql_profiles import MssqlProfile, MssqlProfileError, MssqlProfileManager
from .validator import QueryValidator, ValidationResult

__all__ = [
    "DatabaseInterpreter",
    "DatabaseConnectionError",
    "DatabaseProfileError",
    "DatabaseProfileNotFoundError",
    "DatabaseQuery",
    "DbProfile",
    "DbProfileStore",
    "PostgresConnectionManager",
    "PostgresExecutionError",
    "PostgresExecutionResult",
    "PostgresExecutor",
    "PostgresInterpreter",
    "MssqlExecutionError",
    "MssqlExecutor",
    "MssqlInterpreter",
    "MssqlProfile",
    "MssqlProfileError",
    "MssqlProfileManager",
    "MssqlQueryResult",
    "QueryResult",
    "QueryValidator",
    "SqliteExecutionError",
    "SqliteExecutor",
    "SqliteInterpreter",
    "SqliteProfile",
    "SqliteProfileError",
    "SqliteProfileManager",
    "SqliteProfileNotFoundError",
    "UnsupportedIntentError",
    "ValidationResult",
]
