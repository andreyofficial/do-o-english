#!/usr/bin/env bash
# do-o-english launcher (Linux/macOS).
# First run downloads pip (if missing), creates a venv, installs ursina,
# then launches the game. Subsequent runs just launch instantly.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PY="${DO_O_ENGLISH_PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PY="$candidate"; break
    fi
  done
fi

if [ -z "$PY" ]; then
  echo "Python 3.10+ is required but was not found."
  echo "Install Python 3 from https://python.org and retry."
  exit 1
fi

exec "$PY" "$SCRIPT_DIR/bootstrap.py" run "$@"
