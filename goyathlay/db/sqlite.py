"""Deterministic SQLite translations for local database inspection intents."""

import re

from .base import DatabaseInterpreter, DatabaseQuery, UnsupportedIntentError


class SqliteInterpreter(DatabaseInterpreter):
    """Translate a fixed set of inspection intents into read-only SQLite SQL."""

    ENGINE = "SQLite"

    _QUERIES = {
        "show tables": """SELECT
    name
FROM sqlite_master
WHERE type='table'
ORDER BY name;""",
        "show schema": """SELECT
    type,
    name,
    tbl_name,
    sql
FROM sqlite_master
WHERE type IN ('table', 'view')
ORDER BY type, name;""",
        "show indexes": """SELECT
    name,
    tbl_name
FROM sqlite_master
WHERE type='index'
ORDER BY tbl_name, name;""",
        "show table sizes": """SELECT
    name AS object_name,
    SUM(pgsize) AS size_bytes
FROM dbstat
GROUP BY name
ORDER BY size_bytes DESC, object_name;""",
        "show sqlite version": "SELECT sqlite_version() AS sqlite_version;",
        "show database size": """SELECT
    page_count * page_size AS size_bytes
FROM pragma_page_count(), pragma_page_size();""",
        "show foreign keys": """SELECT
    m.name AS table_name,
    f.id,
    f.seq,
    f."table" AS referenced_table,
    f."from" AS column_name,
    f."to" AS referenced_column
FROM sqlite_master AS m,
     pragma_foreign_key_list(m.name) AS f
WHERE m.type='table'
ORDER BY m.name, f.id, f.seq;""",
        "show triggers": """SELECT
    name
FROM sqlite_master
WHERE type='trigger'
ORDER BY name;""",
        "show views": """SELECT
    name
FROM sqlite_master
WHERE type='view'
ORDER BY name;""",
    }
    _COUNT_ROWS = re.compile(r"count\s+rows\s+in\s+table\s+([A-Za-z_][A-Za-z_0-9]*)\Z", re.IGNORECASE)

    def translate(self, intent: str) -> DatabaseQuery:
        """Translate a supported SQLite inspection request.

        ``count rows in table NAME`` accepts only a simple unqualified SQL
        identifier, which is then quoted in the generated statement.
        """
        if not isinstance(intent, str) or not intent.strip():
            raise UnsupportedIntentError("SQLite intent must not be empty.")
        normalized = " ".join(intent.casefold().split())
        sql = self._QUERIES.get(normalized)
        if sql is None:
            match = self._COUNT_ROWS.fullmatch(" ".join(intent.split()))
            if match is None:
                raise UnsupportedIntentError(f"Unsupported SQLite intent: {intent}")
            table_name = match.group(1).replace('"', '""')
            sql = f'SELECT COUNT(*) AS row_count FROM "{table_name}";'
        return DatabaseQuery(engine=self.ENGINE, intent=intent, sql=sql, read_only=True)
