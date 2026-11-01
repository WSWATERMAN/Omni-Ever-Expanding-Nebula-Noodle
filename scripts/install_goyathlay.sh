#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'ERROR: Python 3.12 or newer is required; python3 was not found.' >&2
    exit 127
fi

exec python3 scripts/install_goyathlay.py "$@"
