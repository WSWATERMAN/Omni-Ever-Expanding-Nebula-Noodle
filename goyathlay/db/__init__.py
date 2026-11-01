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
    "QueryValidator",
    "UnsupportedIntentError",
    "ValidationResult",
]
