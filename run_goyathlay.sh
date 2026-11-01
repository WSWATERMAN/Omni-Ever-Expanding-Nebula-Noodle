#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if command -v python >/dev/null 2>&1; then
    exec python -m goyathlay.goyathlay "$@"
elif command -v python3 >/dev/null 2>&1; then
    exec python3 -m goyathlay.goyathlay "$@"
else
    printf '%s\n' "Goyathlay requires Python 3.12 or later (python or python3)." >&2
    exit 127
fi
