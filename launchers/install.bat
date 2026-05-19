@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% "%SCRIPT_DIR%bootstrap.py" install %*
endlocal
