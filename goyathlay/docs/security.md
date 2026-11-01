# Security review

## Controls present

- Ollama provider is local; no public LLM API integration is part of Goyathlay.
- Commands pass an explicit approval/edit/cancel workflow before execution. Shell execution uses `shlex.split` and `subprocess.run` with `shell=False` semantics.
- SSH uses explicit TOFU enrollment and Paramiko `RejectPolicy`; changed fingerprints are surfaced to the user.
- Persistent stores use private permissions and atomic replacement where applicable; audit/feedback records append to JSONL.
- Policy, RBAC, risk, reputation, blocklist, maintenance windows, SQL validation, and cache eligibility add independent checks.
- SQLite opens read-only and has an authorizer to deny writes.

## Limitations requiring operator controls

- Risk assessment and lexical SQL checks can be bypassed by unrecognized syntax or semantics. They do not sandbox a process or database principal.
- PostgreSQL/MSSQL `SELECT` validation is not sufficient privilege restriction. Use dedicated read-only accounts with narrowly scoped grants. MSSQL `ApplicationIntent=ReadOnly` is a routing hint, not an authorization boundary.
- Password-based database credentials are read from environment variables; use a protected secret manager in production. Do not put secrets in profile JSON.
- SSH known-host approval depends on an informed operator verifying fingerprints out of band.
- Parallel fan-out creates multiple concurrent remote command sessions; cap target groups and account privileges.
- Authentication is not yet integrated into the CLI; default CLI identity remains `local`/ADMIN. Do not treat RBAC as real-user authentication until that work is completed.
- Rollback output is a proposal. It may be incomplete or destructive and must be reviewed and separately approved.
- Meraki operations are descriptors only; if an HTTP client is added, TLS verification, API key storage, organization scoping, timeouts, and audit requirements must be implemented first.

## Release posture

The repository is an alpha-quality development tool, not a certified production security boundary. Keep least-privilege credentials, explicit approval, host verification, and human review enabled. Test against disposable targets before operational use.
