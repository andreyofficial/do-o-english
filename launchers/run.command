#!/usr/bin/env bash
# Double-clickable launcher for macOS Finder.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run.sh" "$@"
