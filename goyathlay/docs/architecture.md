# Goyathlay architecture

Goyathlay is a Python CLI with local Ollama command generation and deterministic local decision modules. `GOYATHLAY_OLLAMA_MODEL` selects a locally installed model; the default is `qwen2.5-coder:14b`. Vendor/database interpreters and SSH/DB connectors are separate from command generation.

```mermaid
flowchart TD
  U[User intent] --> C[SME-approved knowledge lookup]
  C -->|miss| O[Local Ollama]
  C -->|approved environment match| S[Sanitize implementation]
  O --> S
  S --> G[Maintenance and blocklist]
  G --> R[Risk and reputation]
  R --> A[RBAC and profile policy]
  A --> P[Explicit approval]
  P --> X[Local or TOFU SSH execution]
  X --> L[Append-only audit]
  L --> F[Operator result feedback or trainer grade]
  F --> K[Pending knowledge candidate]
  K --> Q[SME review]
  Q -->|approved| C
```

Database query flow is interpreter → validation → explicit approval → engine-specific executor → audit → feedback. SQLite uses Python's standard library; PostgreSQL and MSSQL drivers are optional. Network vendor interpreters currently translate only and do not connect.

Knowledge entries are keyed by intent, environment, implementation type, and implementation. Operator outcomes and trainer grades are evidence only; neither makes an entry reusable. SME approval is required, and an entry with dangerous feedback is excluded from lookup. Legacy cache and feedback records are imported once as pending entries.

## Trust boundaries

- Ollama output is untrusted input. Cleaning only normalizes output; it does not make commands safe.
- Risk scoring, reputation, SQL lexical validation, and blocklists are defense-in-depth, not sandboxes.
- Approval applies to the final edited command, with policy rechecks on shell commands. Operator presentation can hide low/medium risk implementation details, while an explicit execution approval remains mandatory.
- SSH host trust decisions occur before execution. Inventory host overrides select policy profiles. Fan-out preserves sequential enrollment, concurrent execution, stable result ordering, and per-host audit records.
- Authentication and rollback packages are foundations only: the CLI still uses its existing local admin context, and rollback plans are not executed. Persona modes do not authenticate or establish user identity.
