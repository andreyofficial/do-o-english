@echo off
REM do-o-english launcher (Windows).
REM First run downloads pip (if missing), creates a venv, installs ursina,
REM then launches the game. Subsequent runs just launch instantly.

setlocal EnableDelayedExpansion
set "SCRIPT_DIR=%~dp0"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if !ERRORLEVEL!==0 (
        set "PY=python"
    ) else (
        echo Python 3.10+ is required but was not found.
        echo Install Python 3 from https://python.org and retry.
        pause
        exit /b 1
    )
)

%PY% "%SCRIPT_DIR%bootstrap.py" run %*
endlocal
