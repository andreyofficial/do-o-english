# Launchers

Cross-platform launchers and build scripts for **do-o-english**. All scripts here delegate to `bootstrap.py`, which is pure-stdlib Python — it can bootstrap `pip` itself if your system doesn't ship it.

## Run the game

| OS | Command |
|----|---------|
| Linux | `./launchers/run.sh` |
| macOS | double-click `launchers/run.command`, or `./launchers/run.sh` |
| Windows | double-click `launchers\run.bat` |

On first run the launcher:

1. Verifies Python 3.10+ is installed.
2. Creates `.venv/` (downloading `get-pip.py` if pip is missing).
3. Installs Ursina and other deps from `requirements.txt`.
4. Launches the game.

Subsequent runs skip steps 2-3 unless `requirements.txt` changes.

## Other commands

| Script | What it does |
|--------|--------------|
| `install.sh` / `install.bat` | Install deps without launching (useful for offline-prep) |
| `build.sh` / `build.bat` | Build a standalone binary via PyInstaller into `dist/`. Add `--onefile` for a single-file `.exe`-style binary |
| `clean.sh` / `clean.bat` | Remove `.venv/`, `build/`, `dist/`, and the cached `get-pip.py` |
| `install-shortcut.sh` | (Linux) Add `do-o-english` to the app menu + Desktop |

## Environment overrides

- `DO_O_ENGLISH_PYTHON=/path/to/python` — pick which Python the launcher uses.

## Direct usage of bootstrap.py

```bash
python3 launchers/bootstrap.py run         # default
python3 launchers/bootstrap.py install
python3 launchers/bootstrap.py build [--onefile]
python3 launchers/bootstrap.py clean
```

## Notes

- Windows `.exe` files must be built **on Windows**; PyInstaller cannot cross-compile.
- If your distro lacks the `venv` module entirely, the bootstrap will tell you to run:

  ```bash
  sudo apt install -y python3-venv python3-full
  ```

  (`pip` itself is auto-downloaded via `get-pip.py`, but the stdlib `venv` module requires the corresponding system package on Debian/Ubuntu.)
