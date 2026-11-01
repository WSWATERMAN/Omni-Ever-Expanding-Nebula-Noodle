# Goyathlay v1.0.0

This release milestone completes the planned alpha roadmap across local command generation, safety controls, SSH TOFU, database inspection, network translations, dry-run planning, concurrent fan-out, local authentication primitives, and rollback planning.

## Highlights

- Local Ollama-only natural-language command generation.
- Explicit approval and secure local process invocation.
- TOFU-enforced SSH, host inventory, host-specific policies, and parallel multi-host execution after serial enrollment.
- PostgreSQL, SQLite, and MSSQL read-only query paths with validation and auditing.
- Cisco IOS and Aruba translations plus declarative Meraki GET operations.
- Dry-run planning, PBKDF2 local authentication foundation, and advisory rollback plans.

## Qualification

The CLI authentication foundation and rollback framework are not wired to login or execution flows. Vendor device modules are translation-only. Review `goyathlay/docs/security.md` before operational use; the project remains alpha-quality.
