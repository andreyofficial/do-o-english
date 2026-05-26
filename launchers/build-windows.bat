@echo off
REM Build do-o-english.exe on Windows.
REM
REM What this does:
REM   1. Makes sure the project venv exists and pygame + PyInstaller are installed.
REM   2. Runs build.py which calls PyInstaller with the right asset flags.
REM
REM The result is dist\do-o-english.exe (a single self-contained file
REM you can copy to any Windows PC — no Python required to run it).

setlocal EnableDelayedExpansion

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

REM ---- 2. Create / reuse the venv ----
if not exist ".venv\Scripts\python.exe" (
    echo ^>^> Creating virtual environment in .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Could not create the venv.
        pause
        popd
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
)

REM ---- 3. Install pygame + PyInstaller ----
".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" -m pip install pyinstaller>=6.0

REM ---- 4. Build ----
".venv\Scripts\python.exe" build.py
set "EXITCODE=%ERRORLEVEL%"

if %EXITCODE%==0 (
    echo.
    echo Build complete. Your game is at:
    echo     dist\do-o-english.exe
    echo.
    pause
)

popd
endlocal & exit /b %EXITCODE%
