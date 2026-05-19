#!/usr/bin/env python3
"""
do-o-english self-bootstrapping launcher.

Auto-downloads pip (if missing), creates the venv, installs all Python deps,
then launches the game. Uses only Python stdlib so it runs on bare Python 3.

Usage:
    python3 bootstrap.py run        # ensure deps + launch the game (default)
    python3 bootstrap.py install    # ensure deps only
    python3 bootstrap.py build      # build standalone binary via PyInstaller
    python3 bootstrap.py clean      # remove .venv and build artifacts
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
STAMP = VENV / ".deps-installed"
REQ = ROOT / "requirements.txt"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
GET_PIP_LOCAL = ROOT / ".get-pip.py"
MIN_PY = (3, 10)


def info(msg: str) -> None:
    print(f"\033[1;36m>> {msg}\033[0m")


def warn(msg: str) -> None:
    print(f"\033[1;33m!! {msg}\033[0m")


def fail(msg: str, code: int = 1) -> "None":
    print(f"\033[1;31mXX {msg}\033[0m", file=sys.stderr)
    sys.exit(code)


def check_python() -> None:
    if sys.version_info[:2] < MIN_PY:
        fail(
            f"Python {MIN_PY[0]}.{MIN_PY[1]}+ required (have {sys.version.split()[0]}). "
            f"Install a newer Python and re-run."
        )


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def have_module(python: Path, module: str) -> bool:
    try:
        subprocess.run(
            [str(python), "-c", f"import {module}"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def download_get_pip() -> Path:
    if GET_PIP_LOCAL.exists() and GET_PIP_LOCAL.stat().st_size > 0:
        return GET_PIP_LOCAL
    info(f"Downloading get-pip.py from {GET_PIP_URL}")
    try:
        with urllib.request.urlopen(GET_PIP_URL, timeout=30) as resp:
            data = resp.read()
        GET_PIP_LOCAL.write_bytes(data)
    except Exception as exc:
        fail(
            f"Could not download get-pip.py ({exc}).\n"
            f"   Check your internet connection and retry, or place a copy at:\n"
            f"   {GET_PIP_LOCAL}"
        )
    return GET_PIP_LOCAL


def create_venv() -> None:
    if venv_python().exists():
        return
    info("Creating virtual environment in .venv ...")
    if VENV.exists():
        shutil.rmtree(VENV)
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV)],
            check=True,
        )
    except subprocess.CalledProcessError:
        warn("python -m venv failed (likely missing ensurepip). Retrying with --without-pip...")
        if VENV.exists():
            shutil.rmtree(VENV)
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", "--without-pip", str(VENV)],
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            fail(
                "Failed to create virtual environment. On Debian/Ubuntu try:\n"
                "   sudo apt install -y python3-venv python3-full\n"
                f"   Underlying error: {exc}"
            )
    if not venv_python().exists():
        fail("Virtual environment created but python binary missing.")


def ensure_pip_in_venv() -> None:
    py = venv_python()
    if have_module(py, "pip"):
        return
    info("pip missing inside venv; bootstrapping with get-pip.py ...")
    get_pip = download_get_pip()
    subprocess.run([str(py), str(get_pip)], check=True)
    if not have_module(py, "pip"):
        fail("get-pip.py ran but pip still not importable.")


def install_requirements(extra: list[str] | None = None) -> None:
    py = venv_python()
    subprocess.run(
        [str(py), "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    info("Installing dependencies from requirements.txt ...")
    subprocess.run([str(py), "-m", "pip", "install", "-r", str(REQ)], check=True)
    if extra:
        info(f"Installing extras: {' '.join(extra)}")
        subprocess.run([str(py), "-m", "pip", "install", *extra], check=True)
    STAMP.write_text("ok\n", encoding="utf-8")


def deps_up_to_date() -> bool:
    if not STAMP.exists():
        return False
    try:
        return REQ.stat().st_mtime <= STAMP.stat().st_mtime
    except FileNotFoundError:
        return False


def ensure_everything(*, with_pyinstaller: bool = False) -> Path:
    check_python()
    create_venv()
    ensure_pip_in_venv()
    needs_install = not deps_up_to_date()
    if with_pyinstaller:
        py = venv_python()
        if not have_module(py, "PyInstaller"):
            needs_install = True
    if needs_install:
        install_requirements(extra=["pyinstaller>=6.0"] if with_pyinstaller else None)
    return venv_python()


def cmd_run(argv: list[str]) -> None:
    py = ensure_everything()
    info("Launching do-o-english ...")
    main = ROOT / "main.py"
    os.chdir(ROOT)
    os.execv(str(py), [str(py), str(main), *argv])


def cmd_install(_argv: list[str]) -> None:
    ensure_everything()
    info("Dependencies installed. Run `python3 launchers/bootstrap.py run` to start.")


def cmd_build(argv: list[str]) -> None:
    py = ensure_everything(with_pyinstaller=True)
    onefile = "--onefile" in argv
    info("Cleaning previous build artifacts ...")
    for d in ("build", "dist"):
        path = ROOT / d
        if path.exists():
            shutil.rmtree(path)
    sep = ";" if os.name == "nt" else ":"
    if onefile:
        info("Building one-file binary (slower startup) ...")
        subprocess.run(
            [
                str(py), "-m", "PyInstaller",
                "--noconfirm", "--clean",
                "--onefile", "--windowed",
                "--name", "do-o-english",
                "--add-data", f"content{sep}content",
                "main.py",
            ],
            cwd=str(ROOT),
            check=True,
        )
        binary = ROOT / "dist" / ("do-o-english.exe" if os.name == "nt" else "do-o-english")
    else:
        info("Building one-folder app ...")
        subprocess.run(
            [
                str(py), "-m", "PyInstaller",
                "--noconfirm", "--clean",
                "--windowed",
                "--name", "do-o-english",
                "--add-data", f"content{sep}content",
                "main.py",
            ],
            cwd=str(ROOT),
            check=True,
        )
        suffix = ".exe" if os.name == "nt" else ""
        binary = ROOT / "dist" / "do-o-english" / f"do-o-english{suffix}"
    info(f"Built: {binary}")


def cmd_clean(_argv: list[str]) -> None:
    for path in (VENV, ROOT / "build", ROOT / "dist", GET_PIP_LOCAL):
        if path.exists():
            info(f"Removing {path}")
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    info("Clean done.")


COMMANDS = {
    "run": cmd_run,
    "install": cmd_install,
    "build": cmd_build,
    "clean": cmd_clean,
}


def main() -> None:
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "run"
    rest = argv[1:]
    if cmd in {"-h", "--help", "help"}:
        print(__doc__)
        return
    handler = COMMANDS.get(cmd)
    if handler is None:
        fail(f"Unknown command: {cmd}. Use one of: {', '.join(COMMANDS)}")
    handler(rest)


if __name__ == "__main__":
    main()
