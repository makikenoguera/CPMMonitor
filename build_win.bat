@echo off
REM ============================================================
REM  CPM Monitor - Script de compilacion para Windows
REM  Requiere: Python 3.11+, pip install -r requirements_win.txt
REM  Genera: dist\CPMMonitor.exe (onefile, todo incluido)
REM ============================================================

echo [1/2] Instalando dependencias...
pip install -r requirements_win.txt
if %errorlevel% neq 0 (
    echo ERROR: pip install fallo
    pause
    exit /b 1
)

echo [2/2] Compilando con PyInstaller (onefile)...
pyinstaller CPMMonitor_win.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo ERROR: PyInstaller fallo
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Listo!
echo  Ejecutable: dist\CPMMonitor.exe
echo  (Un solo archivo, no necesita instalacion adicional)
echo ============================================================
echo  Sube el archivo al servidor:
echo  monitor.cpmtracks.com/monitor-install/CPMMonitor.exe
echo ============================================================
pause
