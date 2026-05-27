# -*- mode: python ; coding: utf-8 -*-
"""
CPMMonitor.spec — Build macOS
Incluye: sounddevice + PortAudio, numpy, pyacoustid, fpcalc binary
"""
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

# ── fpcalc binary (chromaprint) ───────────────────────────────────────────────
# Buscamos fpcalc en las rutas habituales de Homebrew
_FPCALC_CANDIDATES = [
    "/usr/local/bin/fpcalc",
    "/opt/homebrew/bin/fpcalc",
]
_fpcalc_path = next((p for p in _FPCALC_CANDIDATES if os.path.exists(p)), None)

datas    = [('logo.png', '.'), ('icon.png', '.')]
binaries = []

if _fpcalc_path:
    binaries.append((_fpcalc_path, '.'))   # se copia a la raíz del bundle
    print(f"[SPEC] fpcalc encontrado: {_fpcalc_path}")
else:
    print("[SPEC] ⚠ fpcalc no encontrado — instala: brew install chromaprint")

# ── Hidden imports ────────────────────────────────────────────────────────────
hiddenimports = [
    # UI
    'rumps', 'PyQt5.QtWidgets', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.sip',
    # Core modules
    'core.updater', 'core.scanner', 'core.database', 'core.config',
    'core.sync', 'core.autostart', 'core.permisos', 'core.mensajes',
    'core.spotify_api', 'core.musicbrainz_api',
    'core.audio_capture', 'core.fingerprint', 'core.acrcloud_api',
    # UI modules
    'ui.menu_bar', 'ui.window', 'ui.setup', 'ui.permisos_ui', 'ui.mensaje_ui',
    # Audio
    'sounddevice', 'soundfile', 'numpy', 'acoustid',
    # Stdlib que PyInstaller puede omitir
    'wave', 'tempfile', 'hmac', 'hashlib', 'base64',
]

# ── Collect all para paquetes con recursos ────────────────────────────────────
for pkg in ['rumps', 'sounddevice']:
    tmp = collect_all(pkg)
    datas     += tmp[0]
    binaries  += tmp[1]
    hiddenimports += tmp[2]

# ── PortAudio (necesario para sounddevice) ────────────────────────────────────
_portaudio_candidates = [
    "/usr/local/lib/libportaudio.dylib",
    "/opt/homebrew/lib/libportaudio.dylib",
    "/usr/local/lib/libportaudio.2.dylib",
    "/opt/homebrew/lib/libportaudio.2.dylib",
]
for _pa in _portaudio_candidates:
    if os.path.exists(_pa):
        binaries.append((_pa, '.'))
        print(f"[SPEC] PortAudio: {_pa}")
        break

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CPMMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,   # UPX desactivado — evita corrupción de binarios macOS
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CPMMonitor',
)

app = BUNDLE(
    coll,
    name='CPMMonitor.app',
    icon=None,
    bundle_identifier='com.cpmtracks.monitor',
    info_plist={
        'LSUIElement': True,
        'NSHighResolutionCapable': True,
        'NSPrincipalClass': 'NSApplication',
        # Permisos de audio (requerido macOS 10.14+)
        'NSMicrophoneUsageDescription': 'CPM Monitor necesita acceso al audio para identificar canciones.',
        # Preparado para ScreenCaptureKit (v5.0)
        # 'NSScreenCaptureUsageDescription': 'CPM Monitor captura audio del sistema para identificar canciones.',
    },
)
