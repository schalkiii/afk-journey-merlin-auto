"""检查并安装 GitHub Release 更新。

安全约束（本仓库是 `schalkiii/afk-journey-merlin-auto` 二次开发分支）：
- 更新源只指向本 fork，绝不拉取上游 `yangyh02/...` 的 release；
  否则一次「检查更新」就会把本分支的全部增强覆盖成上游版本。
  需要临时切换仓库时用环境变量 `GAMEBOT_UPDATE_REPO`（格式 owner/repo）。
- 只接受名为 `goldenhandmaidens.exe`、体积不低于 `MIN_EXE_SIZE` 的资产。
- 覆盖运行中的 exe 前先留 `.bak`，批处理失败时回滚，避免产物损坏后无法恢复。
"""

import contextlib
import json
import os
import re
import shutil
import sys
import urllib.request

from version import __version__

# 本 fork 的 Release 源；上游 yangyh02 的版本不含本仓库增强，不能作为更新来源。
UPDATE_REPO = os.environ.get("GAMEBOT_UPDATE_REPO", "schalkiii/afk-journey-merlin-auto")
GITHUB_API = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
EXE_ASSET_NAME = "goldenhandmaidens.exe"
MIN_EXE_SIZE = 1024 * 1024  # 1 MB；低于此值视为错误资产或不完整下载


def _ssl_context():
    try:
        import ssl

        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        import ssl
        return ssl.create_default_context()


def _parse_version(tag):
    m = re.findall(r"\d+", tag)
    return tuple(int(x) for x in m) if m else ()


def _select_exe_asset(assets):
    """从 Release 资产里挑出可安装的 exe，返回 (download_url, size)；不合规则返回 ("", 0)。"""
    for asset in assets or []:
        name = str(asset.get("name", ""))
        url = asset.get("browser_download_url", "")
        try:
            size = int(asset.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if (name.lower().endswith(".exe")
                and EXE_ASSET_NAME.lower() in name.lower()
                and size >= MIN_EXE_SIZE
                and url):
            return url, size
    return "", 0


def check_update():
    """返回四元组 `(has_update, latest_tag, download_url, message)`。

    契约固定为四项：`has_update is None` 表示检查失败，此时 `message` 是错误原因；
    成功但没有可安装资产时 `has_update=False`、`download_url=""`，
    `message` 给出说明。调用方可以统一按四项解包。
    """
    try:
        req = urllib.request.Request(GITHUB_API)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "game-bot-updater")
        with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as resp:
            data = json.loads(resp.read().decode())

        latest_tag = data.get("tag_name", "")
        html_url = data.get("html_url", "")
        download_url, _ = _select_exe_asset(data.get("assets", []))
        has_update = _parse_version(latest_tag) > _parse_version(__version__)
        if has_update and not download_url:
            return False, latest_tag, "", (
                f"{latest_tag} 未提供可安装的 {EXE_ASSET_NAME} 资产，已跳过更新"
            )
        return has_update, latest_tag, download_url, html_url
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
        return None, "", "", str(e)


def download_update(download_url, progress_callback=None):
    """下载新版本 EXE 到 `.new` 文件；返回临时文件路径，失败返回 None。"""
    if not getattr(sys, "frozen", False):
        return None  # 开发模式下不下载
    try:
        exe_path = sys.executable
        new_path = exe_path + ".new"

        req = urllib.request.Request(download_url)
        req.add_header("User-Agent", "game-bot-updater")
        resp = urllib.request.urlopen(req, timeout=120, context=_ssl_context())

        total = int(resp.headers.get("Content-Length", 0) or 0)
        downloaded = 0

        with open(new_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total > 0:
                    progress_callback(downloaded, total)

        # 下载不完整或拿到错误内容时直接丢弃，绝不交给安装步骤覆盖现有 exe
        if downloaded < MIN_EXE_SIZE or (total and downloaded != total):
            with contextlib.suppress(OSError):
                os.remove(new_path)
            return None
        return new_path
    except (OSError, ValueError, TypeError):
        return None


def install_and_restart(new_path):
    """生成 update.bat 备份→替换→重启；替换失败时从 `.bak` 回滚，然后退出当前进程。"""
    if not getattr(sys, "frozen", False):
        return  # 开发模式下不执行
    exe_path = sys.executable
    backup_path = exe_path + ".bak"
    bat_path = os.path.join(os.path.dirname(exe_path), "update.bat")

    # 先留一份可回退的副本；复制失败就不做覆盖
    try:
        shutil.copy2(exe_path, backup_path)
    except OSError:
        return

    with open(bat_path, "w") as f:
        f.write("@echo off\n")
        f.write(f'set "NEW={new_path}"\n')
        f.write(f'set "EXE={exe_path}"\n')
        f.write(f'set "BAK={backup_path}"\n')
        f.write(":retry\n")
        f.write("timeout /t 3 /nobreak >nul\n")
        f.write('move /y "%NEW%" "%EXE%" >nul 2>&1\n')
        f.write('if exist "%NEW%" goto retry\n')
        # 覆盖失败（或产物缺失）时从备份恢复，绝不留下无法启动的 exe
        f.write('if not exist "%EXE%" (\n')
        f.write('  move /y "%BAK%" "%EXE%" >nul\n')
        f.write("  goto fail\n")
        f.write(")\n")
        f.write('start "" "%EXE%"\n')
        f.write('del "%~f0"\n')
        f.write("exit /b 0\n")
        f.write(":fail\n")
        f.write("echo update failed; original exe restored from .bak\n")
        f.write('del "%~f0"\n')
        f.write("exit /b 1\n")

    os.startfile(bat_path)
    sys.exit(0)
