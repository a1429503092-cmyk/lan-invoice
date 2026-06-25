# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\invoice_tool.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/ui/icons', 'ui/icons'),
    ],
    hiddenimports=[
        # 方法内延迟导入（PyInstaller 静态分析可能遗漏）
        'ui.theme',
        'ui.dialogs.pdf_viewer',
        'ui.dialogs.add_attachment',
        'ui.dialogs.attachment_viewer',
        'services.export_service',
        # 核心依赖
        'database',
        'backup',
        'config_manager',
        'invoice_parser',
        'models',
        'repository',
        'filters',
        'utils',
        'worker',
        'logger',
        'version',
        # 对话框模块
        'ui.dialogs.image_viewer',
        'ui.dialogs.settings',
        'ui.dialogs.delete_confirm',
        'ui.dialogs.contract_manager',
        'ui.dialogs.invoice_manager',
        # 第三方隐式依赖
        'pdfplumber',
        'openpyxl',
        'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
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
)
