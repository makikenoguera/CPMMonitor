@echo off
REM ============================================================
REM  CPM Monitor - Script de compilacion para Windows
REM  Requiere: Python 3.10+, pip install -r requirements_win.txt
REM ============================================================

echo [1/3] Instalando dependencias...
pip install -r requirements_win.txt
if %errorlevel% neq 0 (
    echo ERROR: pip install fallo
    pause
    exit /b 1
)

echo [2/3] Compilando con PyInstaller...
pyinstaller CPMMonitor_win.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo ERROR: PyInstaller fallo
    pause
    exit /b 1
)

echo [3/3] Empaquetando en ZIP...
if exist "dist\CPMMonitor_v4.3_win.zip" del /f "dist\CPMMonitor_v4.3_win.zip"
powershell -Command "Compress-Archive -Path 'dist\CPMMonitor\*' -DestinationPath 'dist\CPMMonitor_v4.3_win.zip'"

echo.
echo ============================================================
echo  Listo!
echo  Ejecutable:  dist\CPMMonitor\CPMMonitor.exe
echo  ZIP:         dist\CPMMonitor_v4.3_win.zip
echo ============================================================
echo  Sube ambos archivos al servidor:
echo  monitor.cpmtracks.com/monitor-install/
echo ============================================================
pause
