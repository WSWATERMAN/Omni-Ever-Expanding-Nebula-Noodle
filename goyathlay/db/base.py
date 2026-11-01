"""Database interpreter interface and shared query model."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .validator import QueryValidator, ValidationResult


class UnsupportedIntentError(ValueError):
    """Raised when an interpreter does not recognize a natural-language intent."""


@dataclass(frozen=True)
class DatabaseQuery:
    """A deterministic SQL translation and its intended access mode."""

    engine: str
    intent: str
    sql: str
    read_only: bool


class DatabaseInterpreter(ABC):
    """Base interface for local natural-language database interpreters."""

    def __init__(self, validator: QueryValidator | None = None) -> None:
        """Set the SQL validator used by this interpreter."""
        self._validator = validator or QueryValidator()

    @abstractmethod
    def translate(self, intent: str) -> DatabaseQuery:
        """Translate a supported intent into a database query."""

    def validate(self, sql: str) -> ValidationResult:
        """Validate SQL with the interpreter's configured validator."""
        return self._validator.validate(sql)
