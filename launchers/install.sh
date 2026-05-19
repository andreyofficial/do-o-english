#!/usr/bin/env bash
# Install dependencies only (no launch). Useful for offline-prep.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${DO_O_ENGLISH_PYTHON:-python3}"
exec "$PY" "$SCRIPT_DIR/bootstrap.py" install "$@"
