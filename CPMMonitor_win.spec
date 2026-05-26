# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec para Windows — onedir (Inno Setup crea el instalador final)

from PyInstaller.utils.hooks import collect_all

qt5_datas, qt5_binaries, qt5_hidden = collect_all('PyQt5')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=qt5_binaries,
    datas=qt5_datas + [('logo.png', '.'), ('icon_tray.png', '.')],
    hiddenimports=qt5_hidden + [
        'PyQt5',
        'PyQt5.QtWidgets',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.sip',
        'PyQt5.QtSvg',
        'PyQt5.QtXml',
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
        'sqlite3',
        'certifi',
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
    upx=False,
    console=False,
    icon='icon_tray.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='CPMMonitor',
)
