#!/usr/bin/env bash
# do-o-english launcher for Chrome OS (Linux / Crostini).
#
# On a Chromebook, Linux apps live in the Crostini container — a small
# Debian VM. Compared to a regular Linux desktop, you usually need to
# apt-install Python, the venv module, and the SDL2 libraries pygame
# depends on before pygame itself can be installed.
#
# What this script does:
#   1. Detects that we're on Chrome OS / Crostini (or just regular
#      Debian-derived Linux — the steps are the same).
#   2. apt-installs system packages required by pygame (sudo prompt
#      appears once on the very first run).
#   3. Chains into launchers/linux.sh which builds the venv, installs
#      pygame, and launches the game.
#   4. On first run, installs a .desktop entry so the game shows up in
#      the Chrome OS launcher with an icon and you can pin it to the
#      shelf.
#
# Subsequent runs skip apt and the .desktop install — they just launch.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT"

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

# ---- 1. Sanity check ----
if ! command -v apt-get >/dev/null 2>&1; then
    die "This launcher expects a Debian-based system (Crostini / Linux on
   Chrome OS). For other distros, use launchers/linux.sh instead."
fi

# ---- 2. apt-install system packages (only the missing ones) ----
APT_PACKAGES=(
    python3
    python3-venv
    python3-pip
    libsdl2-2.0-0
    libsdl2-image-2.0-0
    libsdl2-mixer-2.0-0
    libsdl2-ttf-2.0-0
    libfreetype6
    libportmidi0
)

missing=()
for pkg in "${APT_PACKAGES[@]}"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
        missing+=("$pkg")
    fi
done

if [ "${#missing[@]}" -gt 0 ]; then
    echo ">> Installing system packages: ${missing[*]}"
    echo "   (you may be asked for your Crostini password)"
    if ! sudo apt-get update; then
        die "apt-get update failed. Check your Crostini network settings."
    fi
    if ! sudo apt-get install -y "${missing[@]}"; then
        die "apt-get install failed. Try running the command above by hand
   to see the full error message."
    fi
fi

# ---- 3. Install a Chrome OS launcher entry on first run ----
# install-chromeos.sh is the canonical "register me with the Chrome OS
# launcher" script — we just delegate to it so there's only one copy of
# the .desktop / icon logic.
DESKTOP_FILE="$HOME/.local/share/applications/do-o-english.desktop"
if [ ! -f "$DESKTOP_FILE" ] && [ -x "$SCRIPT_DIR/install-chromeos.sh" ]; then
    "$SCRIPT_DIR/install-chromeos.sh" || true
fi

# ---- 4. Hand off to the regular Linux launcher ----
exec "$SCRIPT_DIR/linux.sh" "$@"
