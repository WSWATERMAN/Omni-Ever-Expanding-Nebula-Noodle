"""Deterministic PostgreSQL translations for a small set of inspection intents."""

from .base import DatabaseInterpreter, DatabaseQuery, UnsupportedIntentError


class PostgresInterpreter(DatabaseInterpreter):
    """Translate supported inspection requests into fixed PostgreSQL queries."""

    ENGINE = "PostgreSQL"

    _QUERIES = {
        "show databases": """SELECT
    datname
FROM pg_database
ORDER BY datname;""",
        "show tables": """SELECT
    table_schema,
    table_name
FROM information_schema.tables
ORDER BY table_schema, table_name;""",
        "show largest tables": """SELECT
    schemaname,
    tablename,
    pg_size_pretty(
        pg_total_relation_size(
            schemaname||'.'||tablename
        )
    ) AS size
FROM pg_tables
ORDER BY
    pg_total_relation_size(
        schemaname||'.'||tablename
    ) DESC
LIMIT 10;""",
        "show active sessions": """SELECT
    pid,
    usename,
    state,
    query
FROM pg_stat_activity;""",
        "show blocking sessions": """SELECT
    blocked.pid AS blocked_pid,
    blocked.usename AS blocked_user,
    blocking.pid AS blocking_pid,
    blocking.usename AS blocking_user,
    blocked.query AS blocked_query,
    blocking.query AS blocking_query
FROM pg_stat_activity AS blocked
JOIN pg_locks AS blocked_lock
    ON blocked_lock.pid = blocked.pid
   AND NOT blocked_lock.granted
JOIN pg_locks AS blocking_lock
    ON blocking_lock.locktype = blocked_lock.locktype
   AND blocking_lock.database IS NOT DISTINCT FROM blocked_lock.database
   AND blocking_lock.relation IS NOT DISTINCT FROM blocked_lock.relation
   AND blocking_lock.page IS NOT DISTINCT FROM blocked_lock.page
   AND blocking_lock.tuple IS NOT DISTINCT FROM blocked_lock.tuple
   AND blocking_lock.virtualxid IS NOT DISTINCT FROM blocked_lock.virtualxid
   AND blocking_lock.transactionid IS NOT DISTINCT FROM blocked_lock.transactionid
   AND blocking_lock.classid IS NOT DISTINCT FROM blocked_lock.classid
   AND blocking_lock.objid IS NOT DISTINCT FROM blocked_lock.objid
   AND blocking_lock.objsubid IS NOT DISTINCT FROM blocked_lock.objsubid
   AND blocking_lock.pid <> blocked_lock.pid
   AND blocking_lock.granted
JOIN pg_stat_activity AS blocking
    ON blocking.pid = blocking_lock.pid
ORDER BY blocked.pid;""",
        "show long running queries": """SELECT
    pid,
    usename,
    state,
    query_start,
    now() - query_start AS duration,
    query
FROM pg_stat_activity
WHERE state = 'active'
  AND query_start IS NOT NULL
ORDER BY query_start;""",
        "show database size": """SELECT
    datname AS database_name,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;""",
        "show index usage": """SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY schemaname, relname, indexrelname;""",
        "show table sizes": """SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;""",
        "show replication status": """SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_stat_replication
ORDER BY application_name, pid;""",
    }

    def translate(self, intent: str) -> DatabaseQuery:
        """Return the fixed SQL translation for an exact supported intent.

        Matching ignores surrounding whitespace and letter case. The original
        intent text is retained in the returned query for display and auditing.
        """
        if not isinstance(intent, str) or not intent.strip():
            raise UnsupportedIntentError("Database intent must not be empty.")
        normalized = " ".join(intent.casefold().split())
        try:
            sql = self._QUERIES[normalized]
        except KeyError as exc:
            raise UnsupportedIntentError(f"Unsupported PostgreSQL intent: {intent}") from exc
        return DatabaseQuery(engine=self.ENGINE, intent=intent, sql=sql, read_only=True)
