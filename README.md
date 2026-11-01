# Goyathlay

Goyathlay is a local-first shell and infrastructure assistant under active development. Natural-language command generation uses a local Ollama server; generated shell commands require explicit review before execution. Database and SSH operations add their own validation, trust, approval, and audit boundaries.

The repository also retains the original `akasha.py` application and installer. Goyathlay development does not remove that legacy functionality.

## Requirements

- Python 3.12 or later
- A locally installed Ollama server and a pulled local model for natural-language shell prompts
- Optional: PostgreSQL `psycopg` or SQL Server `pyodbc` driver for those database integrations
- Optional: an ODBC SQL Server driver for the host operating system

No public LLM provider is used. Ollama itself must be available locally. SSH, database, and Meraki API operations naturally require access to their target services when used.

## Install and run

```sh
python3 -m venv .venv-goyathlay
source .venv-goyathlay/bin/activate
pip install -r requirements.txt
python -c "import ollama; print('OK')"
ollama pull qwen2.5-coder:7b
export GOYATHLAY_OLLAMA_MODEL=qwen2.5-coder:7b
python -m goyathlay.goyathlay
```

The provider defaults to `qwen2.5-coder:14b`. Set `GOYATHLAY_OLLAMA_MODEL=qwen2.5-coder:7b` (or another locally pulled model) to select a different model. Optional drivers can be installed separately, for example `python3 -m pip install 'psycopg[binary]'` or `python3 -m pip install pyodbc`.

At startup, Goyathlay reports a missing Ollama Python package with an installation command. Before generating a command, it also checks that the local Ollama daemon responds and that the selected model is installed. Install the `ollama` Python package in the same activated environment used to launch Goyathlay.

On macOS, the system commonly provides `python3` but no `python` command. A freshly created and activated virtual environment includes its own `python` command. You can also use `python3` explicitly after activation. To run without activating the environment, use `python3 -m venv .venv-goyathlay` once, install the requirements with `.venv-goyathlay/bin/python -m pip install -r goyathlay/requirements.txt`, then launch with `.venv-goyathlay/bin/python -m goyathlay.goyathlay`.

Virtual environments are specific to their Python installation and operating system; do not copy one between machines. If `.venv-goyathlay` was copied from another host, recreate it on this Mac with `python3 -m venv --clear .venv-goyathlay`, then repeat the install commands above. Alternatively, run `./run_goyathlay.sh`, which selects `python` when available and otherwise uses `python3`.

## Example

```text
goyathlay> show listening ports
Generated Command:
ss -tulpn
Risk: LOW
...
[A] Approve
[E] Edit
[C] Cancel
Selection: A
Return Code: 0
```

The `dryrun>` prefix previews a generated command and local policy result without approving or executing it:

```text
goyathlay> dryrun> show listening ports
DRY RUN — no command was approved or executed.
```

Useful local commands include `profiles`, `profile NAME`, `host-profile HOST PROFILE`, `blocklist`, `maintenance`, `db profiles`, `sqlite profiles`, and `mssql profiles`. Remote execution uses inventory targets such as `remote> server01 show listening ports` or an inventory group.

## Safety and scope

- Local shell execution uses argument arrays and does not use `shell=True`.
- Risk, reputation, blocklist, maintenance, RBAC, policy profiles, and explicit approval apply to shell execution.
- SSH enrolls unknown host fingerprints through explicit TOFU decisions. Parallel fan-out enrolls hosts sequentially before concurrent command execution.
- SQLite queries use read-only connections and validation. PostgreSQL and SQL Server should use database accounts restricted to read-only access. SQL validation is a lexical guard, not a SQL parser or sandbox.
- Meraki support currently describes fixed GET operations only; it does not issue HTTP requests.
- Authentication primitives and rollback plan generation exist, but account login/bootstrap and rollback execution are not integrated into the main CLI.
- This is an alpha/development project, not a production-certified security boundary. Review generated operations and grant least privilege to service accounts.

## Development checks

```sh
python3 -m unittest discover -s goyathlay/tests -v
git diff --check
```

See [docs/architecture.md](goyathlay/docs/architecture.md), [docs/security.md](goyathlay/docs/security.md), [docs/database.md](goyathlay/docs/database.md), [docs/network.md](goyathlay/docs/network.md), and [docs/roadmap.md](goyathlay/docs/roadmap.md).
