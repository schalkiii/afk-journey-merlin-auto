# -*- mode: python ; coding: utf-8 -*-
import glob
import os


a = Analysis(
    ['goldenhandmaidens.py'],
    pathex=[],
    binaries=[],
    datas=[('click_from_file.exe', '.'), ('templates', 'templates'), ('migong_config.json', '.'), ('formations.json', '.'), ('grid_offsets.json', '.')],
    # 自动收集项目内所有顶层脚本模块，新增 flow 脚本无需手改本清单；
    # certifi / keyboard 为第三方包，仍需显式列出。
    hiddenimports=[os.path.splitext(f)[0] for f in glob.glob("*.py")
                   if not f.startswith("_") and f != "goldenhandmaidens.py"] \
                  + ["certifi", "keyboard"],
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
    name='goldenhandmaidens',
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
)
