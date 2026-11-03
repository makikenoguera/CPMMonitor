@echo off
echo ============================================
echo  Building SumarteRed Monitor for Windows
echo ============================================

REM Ensure pip is up to date
python -m pip install --upgrade pip

REM Install runtime dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Install PyInstaller
echo Installing PyInstaller...
pip install pyinstaller

REM Check fpcalc.exe is present
if not exist fpcalc.exe (
    echo ERROR: fpcalc.exe not found in project root.
    echo Download from https://acoustid.org/chromaprint and place it here.
    pause
    exit /b 1
)

REM Build the executable
echo Building executable...
pyinstaller build.spec --clean --noconfirm

if %ERRORLEVEL% neq 0 (
    echo BUILD FAILED
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ============================================
echo  Build complete!
echo  Executable: dist\SumarteRedMonitor.exe
echo ============================================
pause
