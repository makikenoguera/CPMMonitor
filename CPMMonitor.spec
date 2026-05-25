# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('logo.png', '.'), ('icon.png', '.')]
binaries = []
hiddenimports = ['rumps', 'PyQt5.QtWidgets', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.sip', 'core.updater', 'core.scanner', 'core.database', 'core.config', 'core.sync', 'core.autostart', 'core.permisos', 'core.mensajes', 'ui.menu_bar', 'ui.window', 'ui.setup', 'ui.permisos_ui', 'ui.mensaje_ui']
tmp_ret = collect_all('rumps')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


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
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name='CPMMonitor',
)
app = BUNDLE(
    coll,
    name='CPMMonitor.app',
    icon=None,
    bundle_identifier=None,
    info_plist={
        'LSUIElement': True,
        'NSHighResolutionCapable': True,
        'NSPrincipalClass': 'NSApplication',
    },
)
