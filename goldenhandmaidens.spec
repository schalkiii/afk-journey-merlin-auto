# -*- mode: python ; coding: utf-8 -*-
import glob
import os


a = Analysis(
    ['Goldenhandmaidens.py'],
    pathex=[],
    binaries=[],
    datas=[('click_from_file.exe', '.'), ('click_from_file.ahk', '.'), ('templates', 'templates'), ('migong_config.json', '.'), ('formations.json', '.'), ('grid_offsets.json', '.')],
    # 自动收集项目内所有顶层脚本模块，新增 flow 脚本无需手改本清单；
    # certifi / keyboard 为第三方包，仍需显式列出。
    # windows_capture 由 common 内部按需 import，静态分析看不到，必须显式声明；
    # 它是可选依赖，缺失时运行期会自动回退普通截图。
    # 排除条件必须与磁盘上的实际文件名大小写一致：glob 返回的是
    # "Goldenhandmaidens.py"，写成全小写会把主模块重复收进 hiddenimports。
    hiddenimports=[os.path.splitext(f)[0] for f in glob.glob("*.py")
                   if not f.startswith("_") and f != "Goldenhandmaidens.py"] \
                  + ["certifi", "keyboard", "windows_capture"],
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
    # 必须要求管理员：游戏以管理员权限运行，非提权进程的 SendInput 会被 UIPI 直接拦掉。
    # 症状极具欺骗性——注入器照常读走坐标文件（所有「点击成功」的判据都成立），
    # 游戏画面一动不动，最后表现为每个任务都超时失败（2026-11-12 实测确认）。
    uac_admin=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
