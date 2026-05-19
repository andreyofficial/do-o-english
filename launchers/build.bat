@echo off
REM Build do-o-english.exe via PyInstaller.
REM Usage:
REM   build.bat            one-folder app
REM   build.bat --onefile  single .exe

setlocal
set "SCRIPT_DIR=%~dp0"
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% "%SCRIPT_DIR%bootstrap.py" build %*
endlocal
