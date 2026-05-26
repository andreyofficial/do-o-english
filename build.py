"""
Build a standalone do-o-english executable with PyInstaller.

Usage (from the project root):

    python build.py

It produces:

    dist/do-o-english.exe          (on Windows)
    dist/do-o-english               (on Linux / macOS)

The bundle includes main.py, network.py, the content/ folder, and the
character PNGs. The game's save file (progress.db) is written to a
per-user folder (%APPDATA% on Windows, ~/.local/share on Linux, etc.)
so multiple users on one machine don't trample each other's progress.

PyInstaller cannot cross-compile — to build the Windows .exe you must
run this script on a Windows machine (or via Wine).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "do-o-english"


def _ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(">> Installing PyInstaller ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"]
        )


def _clean():
    for d in ("build", "dist"):
        p = ROOT / d
        if p.exists():
            print(f">> Removing {p}")
            shutil.rmtree(p)
    spec = ROOT / f"{NAME}.spec"
    if spec.exists():
        spec.unlink()


def _data_args():
    """`--add-data` flags for every asset folder/file the game needs."""
    sep = ";" if os.name == "nt" else ":"
    items = [
        ("content", "content"),
        ("happyfacepng.png", "."),
        ("happyface.png", "."),
        ("sadfacepng.png", "."),
        ("sadface.png", "."),
        ("defaultfacepng.png", "."),
        ("Defaultface.png", "."),
    ]
    args = []
    for src, dest in items:
        src_path = ROOT / src
        if not src_path.exists():
            continue
        args += ["--add-data", f"{src_path}{sep}{dest}"]
    return args


def main():
    _ensure_pyinstaller()
    _clean()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", NAME,
        "--onefile",                 # single self-contained executable
        "--noconfirm",
        # Windowed build: no console pops up behind the game.
        # (Comment this out if you want to see Python errors at run time.)
        "--windowed",
        *_data_args(),
        "main.py",
    ]
    print(">>", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)

    out = ROOT / "dist" / (NAME + (".exe" if os.name == "nt" else ""))
    print()
    if out.exists():
        print(f"Built: {out}")
        if os.name == "nt":
            print("Double-click do-o-english.exe to play. No Python required.")
        else:
            print(f"Run it with:  ./{out.relative_to(ROOT)}")
    else:
        print("Build did not produce an executable — check the log above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
