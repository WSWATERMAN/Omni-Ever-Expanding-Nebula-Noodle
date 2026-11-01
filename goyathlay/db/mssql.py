"""Fixed read-only SQL Server translations."""

from .base import DatabaseInterpreter, DatabaseQuery, UnsupportedIntentError


class MssqlInterpreter(DatabaseInterpreter):
    """Translate supported SQL Server inspection intents without AI or I/O."""

    _QUERIES = {
        "show databases": "SELECT name FROM sys.databases ORDER BY name;",
        "show tables": """SELECT
    SCHEMA_NAME(schema_id) AS schema_name,
    name AS table_name
FROM sys.tables
ORDER BY schema_name, table_name;""",
        "show active sessions": """SELECT
    session_id,
    login_name,
    status,
    command,
    wait_type,
    blocking_session_id
FROM sys.dm_exec_requests
ORDER BY session_id;""",
        "show blocking locks": """SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status
FROM sys.dm_tran_locks
WHERE request_status = 'WAIT'
ORDER BY request_session_id;""",
        "show index usage": """SELECT
    OBJECT_SCHEMA_NAME(i.object_id) AS schema_name,
    OBJECT_NAME(i.object_id) AS table_name,
    i.name AS index_name,
    COALESCE(u.user_seeks, 0) AS user_seeks,
    COALESCE(u.user_scans, 0) AS user_scans,
    COALESCE(u.user_lookups, 0) AS user_lookups,
    COALESCE(u.user_updates, 0) AS user_updates
FROM sys.indexes AS i
LEFT JOIN sys.dm_db_index_usage_stats AS u
    ON u.object_id = i.object_id AND u.index_id = i.index_id
WHERE i.object_id > 0
ORDER BY schema_name, table_name, index_name;""",
        "show database size": """SELECT
    name AS file_name,
    type_desc,
    size * 8 AS size_kb
FROM sys.database_files
ORDER BY name;""",
    }

    def translate(self, intent: str) -> DatabaseQuery:
        """Translate one supported intent, matching case and whitespace loosely."""
        if not isinstance(intent, str) or not intent.strip():
            raise UnsupportedIntentError("SQL Server intent must not be empty.")
        normalized = " ".join(intent.casefold().split())
        try:
            sql = self._QUERIES[normalized]
        except KeyError as exc:
            raise UnsupportedIntentError(f"Unsupported SQL Server intent: {intent}") from exc
        return DatabaseQuery("MSSQL", intent, sql, True)
