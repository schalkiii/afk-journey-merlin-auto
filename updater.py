"""检查 GitHub Release 更新"""
import json
import os
import re
import sys
import urllib.request

from version import __version__

GITHUB_API = "https://api.github.com/repos/yangyh02/afk-journey-merlin-auto/releases/latest"


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


def check_update():
    """返回 (has_update, latest_tag, download_url, html_url)，出错返回 (None, error_msg)"""
    try:
        req = urllib.request.Request(GITHUB_API)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "game-bot-updater")
        with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as resp:
            data = json.loads(resp.read().decode())

        latest_tag = data.get("tag_name", "")
        html_url = data.get("html_url", "")
        assets = data.get("assets", [])
        download_url = assets[0]["browser_download_url"] if assets else ""

        has_update = _parse_version(latest_tag) > _parse_version(__version__)
        return has_update, latest_tag, download_url, html_url
    except Exception as e:
        return None, str(e)


def download_update(download_url, progress_callback=None):
    """下载新版本 EXE 到 .new 文件。返回临时文件路径，失败返回 None。"""
    if not getattr(sys, "frozen", False):
        return None  # 开发模式下不下载
    try:
        exe_path = sys.executable
        new_path = exe_path + ".new"

        req = urllib.request.Request(download_url)
        req.add_header("User-Agent", "game-bot-updater")
        resp = urllib.request.urlopen(req, timeout=120, context=_ssl_context())

        total = int(resp.headers.get("Content-Length", 0))
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

        return new_path
    except Exception:
        return None


def install_and_restart(new_path):
    """创建 update.bat 替换 EXE 并重启，然后退出当前进程"""
    if not getattr(sys, "frozen", False):
        return  # 开发模式下不执行
    exe_path = sys.executable
    bat_path = os.path.join(os.path.dirname(exe_path), "update.bat")

    with open(bat_path, "w") as f:
        f.write("@echo off\n")
        f.write(":retry\n")
        f.write("timeout /t 3 /nobreak >nul\n")
        f.write(f'move /y "{new_path}" "{exe_path}"\n')
        f.write(f'if exist "{new_path}" goto retry\n')
        f.write(f'start "" "{exe_path}"\n')
        f.write("del \"%~f0\"\n")

    os.startfile(bat_path)
    sys.exit(0)
