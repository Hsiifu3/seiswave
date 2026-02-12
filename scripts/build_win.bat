@echo off
REM EQSignalPy Windows Build Script
REM Usage: scripts\build_win.bat

echo ============================================
echo  EQSignalPy Windows Build
echo ============================================

cd /d "%~dp0\.."

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.9+.
    exit /b 1
)

REM Install/upgrade PyInstaller
echo [1/3] Installing PyInstaller...
pip install --upgrade pyinstaller

REM Install project dependencies
echo [2/3] Installing dependencies...
pip install -r requirements.txt
pip install -e .

REM Build
echo [3/3] Building EQSignalPy...
python -m PyInstaller build.spec --noconfirm --clean

if errorlevel 1 (
    echo [ERROR] Build failed!
    exit /b 1
)

echo ============================================
echo  Build complete!
echo  Output: dist\EQSignalPy\
echo ============================================
pause
