"""Conservative, dependency-free validation for single read-only SQL statements."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a syntactic SQL safety check."""

    allowed: bool
    reason: str | None = None


class QueryValidator:
    """Allow SELECT, WITH, and EXPLAIN while rejecting write operations."""

    _LITERALS_AND_COMMENTS = re.compile(
        r"--[^\n]*(?:\n|$)"
        r"|/\*.*?\*/"
        r"|'(?:''|[^'])*'"
        r'|"(?:""|[^"])*"'
        r"|\$([A-Za-z_][A-Za-z_0-9]*|)\$.*?\$\1\$",
        re.DOTALL,
    )
    _FORBIDDEN = frozenset(
        {
            "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER",
            "CREATE", "GRANT", "REVOKE", "COPY", "CALL", "DO", "INTO",
            "ATTACH", "DETACH", "VACUUM",
        }
    )

    def validate(self, sql: str) -> ValidationResult:
        """Return a deterministic allow/deny result for one SQL statement.

        This is a lexical guard, not a full SQL parser or database sandbox.
        Comments and quoted values are removed before checking SQL keywords.
        """
        if not isinstance(sql, str) or not sql.strip():
            return ValidationResult(False, "SQL query must not be empty.")

        sanitized = self._LITERALS_AND_COMMENTS.sub(" ", sql).strip()
        if not sanitized:
            return ValidationResult(False, "SQL query must not be empty.")
        # Permit one optional trailing semicolon, but never multiple statements.
        without_trailer = sanitized[:-1].rstrip() if sanitized.endswith(";") else sanitized
        if ";" in without_trailer:
            return ValidationResult(False, "Only one SQL statement is allowed.")

        tokens = re.findall(r"[A-Za-z_][A-Za-z_0-9$]*", without_trailer.upper())
        if not tokens:
            return ValidationResult(False, "SQL query has no recognized statement.")
        if tokens[0] not in {"SELECT", "WITH", "EXPLAIN"}:
            return ValidationResult(False, "Only SELECT, WITH, and EXPLAIN statements are allowed.")
        blocked = next((token for token in tokens if token in self._FORBIDDEN), None)
        if blocked is not None:
            return ValidationResult(False, f"Disallowed SQL operation: {blocked}.")
        return ValidationResult(True, None)
