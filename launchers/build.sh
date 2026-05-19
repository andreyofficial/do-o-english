#!/usr/bin/env bash
# Build a standalone do-o-english binary using PyInstaller.
# Usage:
#   ./build.sh             one-folder app (recommended)
#   ./build.sh --onefile   single-file binary

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${DO_O_ENGLISH_PYTHON:-python3}"
exec "$PY" "$SCRIPT_DIR/bootstrap.py" build "$@"
