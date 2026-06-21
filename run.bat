@echo off
setlocal

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

if defined PYTHONPATH (
    set "PYTHONPATH=%ROOT_DIR%;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%ROOT_DIR%"
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m seiswave %*
    exit /b %errorlevel%
)

python -m seiswave %*
exit /b %errorlevel%
