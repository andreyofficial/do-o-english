#!/usr/bin/env bash
# Register do-o-english with the Chrome OS app launcher.
#
# On Chrome OS, .desktop files dropped into ~/.local/share/applications/
# inside the Linux (Crostini) container are automatically picked up by
# Chrome OS and added to the app shelf.
#
# What this does:
#   1. Generates an icon (a copy of the default face PNG) at
#      ~/.local/share/icons/do-o-english.png.
#   2. Writes ~/.local/share/applications/do-o-english.desktop pointing
#      at launchers/chromeos.sh.
#   3. Refreshes the desktop database so Chrome OS sees it immediately.
#
# After running this script, the do-o-english app appears in the Chrome
# OS launcher (search for "do-o-english" or look under "Linux apps").

set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

LAUNCHER="$ROOT/launchers/chromeos.sh"
chmod +x "$LAUNCHER"

# 1. Pick an icon. Prefer the transparent "happyface" then "defaultface".
ICON_SRC=""
for candidate in happyfacepng.png defaultfacepng.png happyface.png defaultface.png; do
    if [ -f "$ROOT/$candidate" ]; then
        ICON_SRC="$ROOT/$candidate"
        break
    fi
done
if [ -z "$ICON_SRC" ]; then
    echo "No face PNG found in $ROOT — install will run without an icon." >&2
fi

ICON_DIR="$HOME/.local/share/icons"
ICON_DST="$ICON_DIR/do-o-english.png"
mkdir -p "$ICON_DIR"
if [ -n "$ICON_SRC" ]; then
    cp -f "$ICON_SRC" "$ICON_DST"
fi

# 2. Write the .desktop file.
APP_DIR="$HOME/.local/share/applications"
APP_FILE="$APP_DIR/do-o-english.desktop"
mkdir -p "$APP_DIR"

cat >"$APP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=do-o-english
GenericName=English Learning Game
Comment=Beginner-friendly English learning game (single-player + LAN multiplayer)
Exec=$LAUNCHER
Path=$ROOT
Icon=$ICON_DST
Terminal=false
Categories=Game;Education;Languages;
StartupNotify=true
EOF
chmod +x "$APP_FILE"

# 3. Refresh the desktop database so Chrome OS / GNOME notice the new file.
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

echo
echo "Installed: $APP_FILE"
echo
echo "do-o-english should now appear in the Chrome OS launcher within"
echo "a few seconds (search for 'do-o-english' or look under 'Linux apps')."
echo
echo "To uninstall later:"
echo "    rm \"$APP_FILE\" \"$ICON_DST\""
