"""
CPM Tracks - Instalador de autostart multiplataforma
macOS: LaunchAgent plist
Windows: clave Run en el registro de Windows
"""
import os
import sys
import platform

_IS_WIN = platform.system() == "Windows"

# ── macOS ─────────────────────────────────────────────────────────────────────
PLIST_LABEL = "com.cpmtracks.agent"
PLIST_DIR   = os.path.expanduser("~/Library/LaunchAgents")
PLIST_PATH  = os.path.join(PLIST_DIR, f"{PLIST_LABEL}.plist")

# ── Windows ───────────────────────────────────────────────────────────────────
_REG_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REG_NAME = "CPMMonitor"


def _get_executable():
    return sys.executable


def _get_script_path():
    if getattr(sys, 'frozen', False):
        return None
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'main.py'))


# ── Windows helpers ───────────────────────────────────────────────────────────

def _win_instalar():
    try:
        import winreg
        exe = _get_executable()
        script = _get_script_path()
        if script:
            cmd = f'"{exe}" "{script}" --background'
        else:
            cmd = f'"{exe}" --background'
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, _REG_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        return True, "Autostart activado correctamente"
    except Exception as e:
        return False, str(e)


def _win_desinstalar():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, _REG_NAME)
        winreg.CloseKey(key)
        return True, "Autostart desactivado"
    except FileNotFoundError:
        return True, "Autostart desactivado"
    except Exception as e:
        return False, str(e)


def _win_esta_instalado():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _REG_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


# ── macOS helpers ─────────────────────────────────────────────────────────────

def _mac_instalar():
    import subprocess
    os.makedirs(PLIST_DIR, exist_ok=True)
    exe = _get_executable()
    script = _get_script_path()

    if script:
        program_args = f"""
        <array>
            <string>{exe}</string>
            <string>{script}</string>
            <string>--background</string>
        </array>"""
    else:
        program_args = f"""
        <array>
            <string>{exe}</string>
            <string>--background</string>
        </array>"""

    log_dir = os.path.expanduser("~/Library/Logs/CPMTracks")
    os.makedirs(log_dir, exist_ok=True)

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    {program_args}
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>{log_dir}/agent.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/agent_error.log</string>
</dict>
</plist>"""

    try:
        with open(PLIST_PATH, 'w') as f:
            f.write(plist)
        subprocess.run(['launchctl', 'unload', PLIST_PATH], capture_output=True)
        result = subprocess.run(
            ['launchctl', 'load', '-w', PLIST_PATH],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return False, f"launchctl error: {result.stderr}"
        return True, "Autostart activado correctamente"
    except Exception as e:
        return False, str(e)


def _mac_desinstalar():
    import subprocess
    try:
        if os.path.exists(PLIST_PATH):
            subprocess.run(['launchctl', 'unload', PLIST_PATH], capture_output=True)
            os.remove(PLIST_PATH)
        return True, "Autostart desactivado"
    except Exception as e:
        return False, str(e)


def _mac_esta_instalado():
    return os.path.exists(PLIST_PATH)


# ── API pública ───────────────────────────────────────────────────────────────

def instalar():
    if _IS_WIN:
        return _win_instalar()
    return _mac_instalar()


def desinstalar():
    if _IS_WIN:
        return _win_desinstalar()
    return _mac_desinstalar()


def esta_instalado():
    if _IS_WIN:
        return _win_esta_instalado()
    return _mac_esta_instalado()
