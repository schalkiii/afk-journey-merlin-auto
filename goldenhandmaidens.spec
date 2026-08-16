# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['goldenhandmaidens.py'],
    pathex=[],
    binaries=[],
    datas=[('click_from_file.exe', '.'), ('templates', 'templates'), ('migong_config.json', '.'), ('formations.json', '.'), ('grid_offsets.json', '.')],
    hiddenimports=['shangcheng', 'youyishangcheng', 'common', 'flow_tower', 'jiance', 'warehouse', 'push', 'flow_push', 'mimengzhiyu', 'nvshenta', 'meirirenwulingqu', 'haoyoujiangli', 'youjian', 'shouquguajijiangli', 'start', 'pata', 'pujing', 'flow_migong', 'flow_enter', 'formation', 'drag_utils', 'updater', 'version', 'certifi', 'hero_metadata', 'keyboard'],
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
