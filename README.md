# do-o-english

A beginner-friendly English learning game built with **pygame**.
Single file, one straightforward game loop, every line commented.

## What's inside

- A main menu where you pick an existing profile or register a new one
- Two registration buttons: **Register as Teacher** / **Register as Student**
  - Teacher: last name, first name, class you teach
  - Student: your class, last name, first name
- A hub with a list of lessons
- Lessons with question + multiple-choice answers
- A summary screen at the end with score and XP

Progress is saved to `~/.local/share/do-o-english/progress.db` (a tiny SQLite file).

## Quick start (recommended)

The launchers create a virtual environment and install `pygame` on first run.
There are just two of them:

| OS | Command |
|----|---------|
| **Linux** | `./launchers/linux.sh` |
| **Windows** | double-click `launchers\windows.bat` |
| **Chrome OS** (Crostini) | `./launchers/chromeos.sh` |

On Chrome OS, the first run installs the SDL libraries pygame needs and
adds a launcher entry, so afterwards you can just click **do-o-english**
in the Chrome OS launcher (or pin it to the shelf).
| **Chrome OS** | `./launchers/chromeos.sh` (see Chrome OS notes below) |

## Or run it manually

```bash
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build a Windows `.exe`

If you want a single self-contained `do-o-english.exe` you can send to
someone who doesn't have Python installed, run the build script on a
Windows machine:

```
launchers\build-windows.bat
```

That will:

1. Set up the venv if needed and install pygame + PyInstaller.
2. Bundle `main.py`, `network.py`, the `content/` folder and the
   character PNGs into a single `.exe`.

The result lands at `dist\do-o-english.exe`. Double-click it to play —
no Python required. The save file is written to
`%APPDATA%\do-o-english\progress.db`.

> PyInstaller can't cross-compile, so the `.exe` has to be built on a
> Windows machine (or in Wine).

## Code map

Everything lives in one file you can read top-to-bottom:

```
do-o-english/
├── main.py            ← the whole game (well commented, no surprises)
├── requirements.txt   ← just: pygame
├── content/           ← lesson JSON files (5 café lessons)
└── launchers/         ← linux.sh and windows.bat (auto-install + launch)
```

`main.py` is split into clearly labelled sections:

1. Imports
2. Constants (colors, sizes, paths)
3. Database helpers (SQLite)
4. Content loading (reads `content/*.json`)
5. UI helpers — `Button`, `TextInput`, `draw_text`
6. The `App` class — game loop and every screen
7. Entry point

## Controls

| Where | Keys |
|-------|------|
| Form  | **Tab** / **↑ ↓** switch field   ·   **Enter** confirm   ·   **Esc** back |
| Hub   | Click a lesson to start it   ·   **Esc** = log out |
| Lesson | Click an answer button   ·   **Esc** = quit lesson |

## License

For personal learning use.
