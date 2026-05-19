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

| OS | Command |
|----|---------|
| **Linux** | `./launchers/run.sh` |
| **macOS** | double-click `launchers/run.command` |
| **Windows** | double-click `launchers\run.bat` |

## Or run it manually

```bash
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Code map

Everything lives in one file you can read top-to-bottom:

```
do-o-english/
├── main.py            ← the whole game (well commented, no surprises)
├── requirements.txt   ← just: pygame
├── content/           ← lesson JSON files (5 café lessons)
└── launchers/         ← auto-installing launch & build scripts
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
