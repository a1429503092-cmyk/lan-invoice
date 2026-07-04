# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\invoice_tool.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/ui/icons', 'ui/icons'),
    ],
    hiddenimports=[
        'ui.theme',
        'ui.dialogs.pdf_viewer',
        'ui.dialogs.add_attachment',
        'ui.dialogs.attachment_viewer',
        'ui.dialogs.image_viewer',
        'ui.dialogs.settings',
        'ui.dialogs.delete_confirm',
        'ui.dialogs.contract_manager',
        'ui.dialogs.invoice_manager',
        'ui.dialogs.import_preview',
        'ui.widgets.strategy_card',
        'services.export_service',
        'services.invoice_service',
        'database', 'backup', 'config_manager',
        'invoice_parser', 'models', 'repository',
        'filters', 'utils', 'worker',
        'logger', 'version', 'storage',
        'pdfplumber', 'openpyxl', 'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PIL', 'Pillow',            # pdfplumber 图片提取，发票解析不需要
        'tkinter', 'tcl',           # 不使用 tkinter
        'PyQt5.QtMultimedia',       # 不需要音频/视频
        'PyQt5.QtWebEngine',        # 不需要浏览器引擎
        'PyQt5.QtBluetooth',        # 不需要蓝牙
        'PyQt5.QtNfc',              # 不需要 NFC
        'PyQt5.QtPositioning',      # 不需要定位
        'PyQt5.QtQuick',            # 不需要 QML
        'PyQt5.QtRemoteObjects',    # 不需要远程对象
        'PyQt5.QtSensors',          # 不需要传感器
        'PyQt5.QtSerialPort',       # 不需要串口
        'PyQt5.QtSql',              # 不需要 Qt SQL
        'PyQt5.QtSvg',              # 不需要 SVG
        'PyQt5.QtTest',             # 不需要测试模块
        'PyQt5.QtWebChannel',       # 不需要 WebChannel
        'PyQt5.QtXml',              # 不需要 XML 解析
        'PyQt5.QtXmlPatterns',      # 不需要 XSLT
    ],
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
    name='发票归档',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
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
    version='version_info.txt',
)
