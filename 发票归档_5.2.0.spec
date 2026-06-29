# -*- mode: python ; coding: utf-8 -*-

# 未使用的 PyQt5 模块（排除以减小体积）
UNUSED_QT_MODULES = [
    'PyQt5.QtQuick', 'PyQt5.QtQml', 'PyQt5.QtMultimedia',
    'PyQt5.QtMultimediaWidgets', 'PyQt5.QtBluetooth', 'PyQt5.QtLocation',
    'PyQt5.QtSensors', 'PyQt5.QtNfc', 'PyQt5.QtDesigner',
    'PyQt5.QtHelp', 'PyQt5.QtDBus', 'PyQt5.QtRemoteObjects',
    'PyQt5.QtTest', 'PyQt5.QtOpenGL', 'PyQt5.QtPositioning',
    'PyQt5.QtXmlPatterns', 'PyQt5.QtTextToSpeech',
    'PyQt5.QtWebChannel', 'PyQt5.QtWebSockets',
    'PyQt5.QtSerialPort', 'PyQt5.QAxContainer',
    'PyQt5.QtQuick3D', 'PyQt5.QtQuickWidgets',
]

a = Analysis(
    ['src\\invoice_tool.py'],
    pathex=['src'],
    binaries=[],
    datas=[('src/ui/icons', 'ui/icons')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=UNUSED_QT_MODULES,
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='发票归档_5.2.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
