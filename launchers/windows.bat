@echo off
REM do-o-english launcher for Windows.
REM
REM What this does:
REM   1. Finds your Python 3 (any version >= 3.10 works).
REM   2. On the first run, creates a virtual environment in .\.venv
REM      and installs pygame inside it.
REM   3. Launches the game.
REM
REM Subsequent runs just launch the game instantly.

setlocal EnableDelayedExpansion

REM Always run from the project root (the folder above this script).
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.."

REM ---- 1. Find a Python 3 interpreter ----
set "PY="
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if !ERRORLEVEL!==0 (
        set "PY=python"
    )
)
if not defined PY (
    echo Python 3 is required but was not found.
    echo Install it from https://python.org and check "Add Python to PATH".
    pause
    popd
    exit /b 1
)

REM ---- 2. Create the venv if it's not there yet ----
if not exist ".venv\Scripts\python.exe" (
    echo ^>^> Creating virtual environment in .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Could not create the venv.
        echo Please reinstall Python and check "Add Python to PATH" during setup.
        pause
        popd
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
)

REM ---- 3. Install requirements if pygame isn't importable yet ----
".venv\Scripts\python.exe" -c "import pygame" >nul 2>nul
if errorlevel 1 (
    echo ^>^> Installing requirements ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Failed to install requirements.
        pause
        popd
        exit /b 1
    )
)

REM ---- 4. Launch the game ----
".venv\Scripts\python.exe" main.py %*
set "EXITCODE=%ERRORLEVEL%"

popd
endlocal & exit /b %EXITCODE%
