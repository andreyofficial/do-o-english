#!/usr/bin/env bash
# Wipe .venv, build, dist, and the cached get-pip.py.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${DO_O_ENGLISH_PYTHON:-python3}"
exec "$PY" "$SCRIPT_DIR/bootstrap.py" clean "$@"
