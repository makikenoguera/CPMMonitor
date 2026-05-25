# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec para Windows — genera CPMMonitor.exe (onedir, sin consola)

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('logo.png', '.'), ('icon_tray.png', '.')],
    hiddenimports=[
        'PyQt5.QtWidgets',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.sip',
        'core.updater',
        'core.scanner_win',
        'core.database',
        'core.config',
        'core.sync',
        'core.autostart',
        'core.mensajes',
        'ui.tray_win',
        'ui.window',
        'ui.setup',
        'ui.mensaje_ui',
        'ui.banner_ui',
        'winreg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['rumps', 'AppKit', 'Foundation', 'objc', 'PyQt6'],
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
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon_tray.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CPMMonitor',
)
