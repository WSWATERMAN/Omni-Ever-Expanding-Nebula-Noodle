#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

VENV=${GOYATHLAY_VENV:-"$SCRIPT_DIR/.venv-goyathlay"}
VENV_PYTHON="$VENV/bin/python"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

if [ -L "$VENV" ]; then
    printf '%s\n' "ERROR: Refusing to use a symbolic-link virtual environment: $VENV" >&2
    exit 1
fi

if [ ! -e "$VENV" ]; then
    BOOTSTRAP_PYTHON=
    if command -v python3 >/dev/null 2>&1; then
        BOOTSTRAP_PYTHON=$(command -v python3)
    elif command -v python >/dev/null 2>&1; then
        BOOTSTRAP_PYTHON=$(command -v python)
    else
        printf '%s\n' 'ERROR: Python 3.12 or later is required (python3 or python).' >&2
        exit 127
    fi
    if ! "$BOOTSTRAP_PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' 2>/dev/null; then
        printf '%s\n' 'ERROR: Python 3.12 or later is required to create the Goyathlay environment.' >&2
        exit 1
    fi
    printf '%s\n' 'Creating Goyathlay virtual environment...'
    "$BOOTSTRAP_PYTHON" -m venv "$VENV"
fi

if [ ! -x "$VENV_PYTHON" ]; then
    printf '%s\n' "ERROR: The Goyathlay virtual environment is incomplete: $VENV_PYTHON is unavailable." >&2
    printf '%s\n' 'Repair it with: python3 scripts/install_goyathlay.py' >&2
    exit 1
fi

if ! "$VENV_PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' 2>/dev/null; then
    printf '%s\n' 'ERROR: The Goyathlay virtual environment requires Python 3.12 or later.' >&2
    printf '%s\n' 'Repair it with: python3 scripts/install_goyathlay.py' >&2
    exit 1
fi

if ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
    printf '%s\n' 'Repairing pip in the Goyathlay virtual environment...'
    "$VENV_PYTHON" -m ensurepip --upgrade
fi

if ! "$VENV_PYTHON" -c 'import ollama, paramiko, prompt_toolkit' >/dev/null 2>&1; then
    if [ ! -f "$REQUIREMENTS" ]; then
        printf '%s\n' "ERROR: Dependency file is missing: $REQUIREMENTS" >&2
        exit 1
    fi
    printf '%s\n' 'Installing Goyathlay Python dependencies...'
    if ! "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS"; then
        printf '%s\n' 'ERROR: Dependency installation failed. Check your network and pip output, then retry.' >&2
        exit 1
    fi
fi

if ! "$VENV_PYTHON" -c 'import ollama' >/dev/null 2>&1; then
    printf '%s\n' 'ERROR: The Ollama Python package is still unavailable in .venv-goyathlay.' >&2
    printf '%s\n' 'Try: .venv-goyathlay/bin/python -m pip install ollama' >&2
    exit 1
fi

exec "$VENV_PYTHON" -m goyathlay.goyathlay "$@"
