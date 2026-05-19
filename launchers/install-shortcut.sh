#!/usr/bin/env bash
# Install the do-o-english launcher into the Linux app menu and Desktop.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_SRC="$SCRIPT_DIR/do-o-english.desktop"

chmod +x "$SCRIPT_DIR/run.sh" "$SCRIPT_DIR/build.sh" "$SCRIPT_DIR/install.sh" "$SCRIPT_DIR/clean.sh" 2>/dev/null || true

APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
cp "$DESKTOP_SRC" "$APPS_DIR/do-o-english.desktop"
chmod +x "$APPS_DIR/do-o-english.desktop"

DESKTOP_DIR="$HOME/Desktop"
if [ -d "$DESKTOP_DIR" ]; then
  cp "$DESKTOP_SRC" "$DESKTOP_DIR/do-o-english.desktop"
  chmod +x "$DESKTOP_DIR/do-o-english.desktop"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

echo "Installed shortcut:"
echo "  - $APPS_DIR/do-o-english.desktop"
[ -d "$DESKTOP_DIR" ] && echo "  - $DESKTOP_DIR/do-o-english.desktop"
echo
echo "Right-click the Desktop icon and choose 'Allow Launching' if your file manager asks."
