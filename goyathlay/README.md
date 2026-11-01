# Goyathlay

Next-generation local-first successor to Akasha.

Goals

- Local-only AI
- Ollama backend
- No public LLM access
- Approval workflow
- TOFU SSH trust
- Audit logging
- Secure execution boundaries
- Curated, environment-aware operational knowledge

## Operator, trainer, and SME workflows

The default `operator` persona keeps generated implementations out of view for
LOW and MEDIUM risk operations. Goyathlay still requires explicit execution
approval; the prompt asks the operator to approve the requested operation
without displaying the underlying command. After results, the operator can
mark them successful, unsuccessful, dangerous, or skipped. HIGH risk operations
show the command and the existing risk and policy controls.

Switch personas at the prompt:

```text
mode operator
mode trainer
mode sme
```

Trainer mode shows the implementation and output, then collects a 0–5 grade
and optional note. `trainer queue` lists pending candidates. SME mode accepts
`sme review`, where candidates can be approved, rejected, replaced, or annotated.
`knowledge stats` reports counts and ranked implementations.

Knowledge is stored at `~/.goyathlay/knowledge.json`. Implementations are keyed
by intent and environment (for example `local`, `remote`, `postgres`, `sqlite`,
or `mssql`). Only SME-approved entries with no dangerous operator reports are
eligible for automatic lookup. Legacy command-cache and feedback data is
imported once; imported entries remain pending and are never trusted by migration.

RBAC defines separate operator, trainer, SME, and admin learning permissions.
The current CLI uses its existing local `ADMIN` context and does not authenticate
people; persona selection is a workflow choice, not an identity check. Do not
treat local RBAC as an organizational login boundary.

Roadmap

v0.1
- Ollama provider abstraction

v0.2
- Approve / Edit / Cancel workflow

v0.3
- TOFU SSH enrollment

v0.4
- Audit logging

v1.0
- Production-ready release
