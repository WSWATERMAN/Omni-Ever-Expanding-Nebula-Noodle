# Database integrations

## Current support

| Engine | Interpreter | Profiles | Execution | Driver |
|---|---|---|---|---|
| PostgreSQL | Fixed read-only inspection intents | Private JSON | Transaction rollback after fetch | Optional `psycopg` |
| SQLite | Fixed inspection intents | Private JSON | URI read-only connection and write-denying authorizer | Python `sqlite3` |
| Microsoft SQL Server | Fixed inspection intents | Private JSON, password excluded | ODBC read-only intent, no autocommit, rollback | Optional `pyodbc` plus system ODBC driver |

SQL prompt forms: `db> [PROFILE] show tables`, `sqlite> [PROFILE] show tables`, and `mssql> [PROFILE] show tables`. Profile commands are `db profiles`, `sqlite profiles`, `mssql profiles`; `db profile NAME`, `sqlite profile NAME`, and `mssql profile NAME` switch defaults.

All queries are shown for explicit approval. Edited queries are validated again. Audit records include engine, profile, endpoint/path, row count, and success. Failed execution is audited; cancelled queries are not executed.

## Security notes

The common validator is a conservative lexical guard, not a full parser. It allows SELECT/WITH/EXPLAIN and blocks known write tokens and multiple statements. Use dedicated read-only users regardless of validation. SQL Server `ApplicationIntent=ReadOnly` is not an access-control guarantee. Use encrypted connections with certificate validation; the MSSQL executor sets `Encrypt=yes` and `TrustServerCertificate=no`.

Drivers are optional to keep base installation light. Install `psycopg[binary]` or `pyodbc` only for the relevant engine; platform ODBC driver installation is separate.
