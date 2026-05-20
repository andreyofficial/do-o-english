#!/usr/bin/env bash
# do-o-english launcher for Linux.
#
# What this does:
#   1. Finds your Python 3 (any version >= 3.10 works).
#   2. On the first run, creates a virtual environment in ./.venv
#      and installs pygame inside it.
#   3. Launches the game.
#
# Subsequent runs just launch the game instantly.

# Always run from the project root (the folder above this script).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

# If anything below fails, hang the terminal open so the user can read the
# error message before the window closes. (Only does the pause if we are
# attached to a real terminal.)
die() {
    echo
    echo "!! do-o-english couldn't start."
    echo "   $1"
    echo
    if [ -t 0 ]; then
        printf "Press Enter to close this window. "
        read -r _ || true
    fi
    exit 1
}

# ---- 1. Find a Python 3 interpreter ----
PY=""
for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    die "Python 3 is required but was not found.
   Install it with:  sudo apt install python3 python3-venv"
fi

# ---- 2. Create the venv if it's not there yet ----
if [ ! -x ".venv/bin/python" ]; then
    echo ">> Creating virtual environment in .venv ..."
    if ! "$PY" -m venv .venv; then
        die "Could not create the venv.
   On Debian / Ubuntu / Zorin OS, try:
       sudo apt install python3-venv python3-full"
    fi
    .venv/bin/python -m pip install --upgrade pip >/dev/null || true
fi

# ---- 3. Install requirements if pygame isn't importable yet ----
if ! .venv/bin/python -c "import pygame" >/dev/null 2>&1; then
    echo ">> Installing requirements (pygame) ..."
    if ! .venv/bin/python -m pip install -r requirements.txt; then
        die "pip install failed.
   Check your internet connection, then run me again from a terminal:
       cd \"$ROOT\" && ./launchers/linux.sh"
    fi
fi

# ---- 4. Launch the game ----
exec .venv/bin/python main.py "$@"
