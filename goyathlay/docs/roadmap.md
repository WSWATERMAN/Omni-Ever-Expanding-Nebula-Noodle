# Roadmap and implementation status

## Delivered in the v1.0 roadmap

- Local Ollama provider, sanitizer, approval, controlled shell execution, feedback, verified cache, risk/reputation/policy, RBAC, blocklist, maintenance windows, and audit records.
- SSH TOFU enrollment, remote execution, inventory and groups, and concurrent fan-out after serial host enrollment.
- PostgreSQL, SQLite, and MSSQL query translation/profile/execution modules. SQLite is read-only at the connection layer; PostgreSQL and MSSQL require least-privilege read-only server accounts.
- Cisco IOS and Aruba allowlisted read-only translations; Meraki fixed GET operation descriptors.
- Local command dry-run planning, per-host policy profile overrides, local PBKDF2 authentication primitives, and rollback plan generation.

## Known incomplete integrations

- Authentication needs a first-run administrator enrollment, CLI login, and wiring into `UserContext` before it can enforce real identities.
- Rollback plans are advisory only and require independent approval and execution workflows.
- Cisco/Aruba translators are not connected to SSH or the CLI. Meraki does not make API calls.
- No live SQL Server or external network device integration was exercised by the unit suite.
- Existing Akasha remains in the repository and has not been rewritten.

## Follow-on work

- Integrate auth enrollment and login without breaking existing local installations.
- Add a structured command AST/policy layer and stronger OS/database isolation.
- Provide an approved device execution connector and vendor-specific configuration risk policies.
- Add integration tests against disposable database/device fixtures.
- Add key/secret vault support, session expiry, and credential rotation.
- Define cache invalidation, role administration, and multi-user audit attribution.
