#!/usr/bin/env bash
# do-o-english desktop launcher.
#
# Invoked by ~/Desktop/do-o-english.desktop. Strategy:
#   1. If the venv + pygame are already set up, launch the game silently.
#   2. If anything is missing (no venv, no pygame), open a terminal so the
#      first-run install is visible.
#   3. If the silent launch fails for any reason, reopen in a terminal so
#      the user sees the error instead of staring at a frozen icon.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PY="$ROOT/.venv/bin/python"
LAUNCHER="$ROOT/launchers/linux.sh"
LOG_DIR="$HOME/.local/share/do-o-english"
LOG_FILE="$LOG_DIR/launch.log"
mkdir -p "$LOG_DIR"

# Pick the first terminal emulator that's installed.
pick_terminal() {
    for term in x-terminal-emulator gnome-terminal konsole \
                xfce4-terminal mate-terminal lxterminal \
                alacritty kitty tilix xterm; do
        if command -v "$term" >/dev/null 2>&1; then
            printf '%s' "$term"
            return 0
        fi
    done
    return 1
}

# Run the inner launcher inside a terminal window so the user can see
# install progress or an error message before the window closes.
run_in_terminal() {
    local term inner
    term="$1"
    inner="cd '$ROOT' && '$LAUNCHER'; status=\$?; echo; \
if [ \$status -ne 0 ]; then echo 'do-o-english exited with error '\$status'.'; fi; \
echo 'Press Enter to close.'; read _"
    case "$term" in
        gnome-terminal|tilix)
            "$term" -- bash -c "$inner"
            ;;
        *)
            "$term" -e bash -c "$inner"
            ;;
    esac
}

needs_setup=0
if [ ! -x "$PY" ] || ! "$PY" -c "import pygame" >/dev/null 2>&1; then
    needs_setup=1
fi

if [ "$needs_setup" -eq 1 ]; then
    # First-run / missing pygame — show the install in a terminal.
    if term=$(pick_terminal); then
        run_in_terminal "$term"
        exit 0
    fi
    # No terminal — best effort silent install.
    exec "$LAUNCHER"
fi

# Normal silent launch with logging. If it crashes, reopen in a terminal.
if "$LAUNCHER" >"$LOG_FILE" 2>&1; then
    exit 0
fi

status=$?
if term=$(pick_terminal); then
    "$term" -e bash -c "echo 'do-o-english failed to start (exit '$status').'; \
echo 'Recent log:'; echo '----'; tail -n 40 '$LOG_FILE'; echo '----'; \
echo 'Press Enter to close.'; read _" || true
fi
exit "$status"
