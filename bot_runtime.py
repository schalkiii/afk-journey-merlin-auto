"""游戏启动 / 配置 / 窗口聚焦等独立工具（从 Goldenhandmaidens 抽出，降低主文件体积）。

这些函数与 GUI 类无耦合，仅依赖标准库与 common 的路径解析，可独立测试与复用。
Goldenhandmaidens 在顶部 `from bot_runtime import (...)` 取回所需符号，保持原引用不变。
"""

import contextlib
import ctypes
import json
import os
import shlex
import subprocess
import sys
from ctypes import wintypes

from common import get_work_path


class _StdoutTee:
    """把 stdout 同时输出到原始 stdout 与面板日志汇聚回调，
    使各子脚本中的 print(...) 调试日志也能显示在应用内「运行日志」面板。"""
    def __init__(self, sink):
        self._sink = sink
        self._orig = sys.__stdout__

    def write(self, s):
        with contextlib.suppress(Exception):
            self._orig.write(s)  # type: ignore[union-attr]
        if s and s.strip():
            with contextlib.suppress(Exception):
                self._sink(s.rstrip("\n"))

    def flush(self):
        with contextlib.suppress(Exception):
            self._orig.flush()  # type: ignore[union-attr]


# 启动早期（GUI 实例创建前）的 stdout 缓冲：窗口模式下 sys.stdout 初始为 None，
# 必须尽早接管 stdout，否则启动期 print 会写入 None 而崩溃。
_early_stdout_buffer = []
def _early_stdout_sink(msg):
    _early_stdout_buffer.append(msg)


CONFIG_FILE = get_work_path("game_bot_config.json")

def load_config():
    """加载配置文件"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
    return {}

def save_config(config):
    """保存配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存配置文件失败: {e}")
        return False

class ScriptConfig:
    def __init__(self, name, enabled=False, params=None, daily_reset=False):
        self.name = name
        self.enabled = enabled
        self.params = params or {}
        self.status = "就绪"
        self.daily_reset = daily_reset  # 是否每日重置
        self.last_run_time: str | None = None  # 最后执行时间

def _ensure_config_files():
    """首次运行时确保 shared 目录存在（坐标 IPC 等文件的工作目录）。

    历史版本曾在此从打包资源复制配置文件到 exe 同目录；现改为 load_config 直接
    读写 game_bot_config.json，无需复制，故仅保留建目录职责、移除空拷贝循环。
    """
    shared_dir = get_work_path("shared")
    os.makedirs(shared_dir, exist_ok=True)


# 桌面快捷方式候选名称（文件名包含其一即视为游戏快捷方式）
GAME_SHORTCUT_KEYWORDS = ["剑与远征", "启程", "afk", "afkj"]


def find_game_shortcut():
    """在用户桌面与公共桌面查找剑与远征：启程的 .lnk 快捷方式。"""
    desktop_dirs = []
    user_profile = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if user_profile:
        desktop_dirs.append(os.path.join(user_profile, "Desktop"))
        desktop_dirs.append(os.path.join(user_profile, "OneDrive", "Desktop"))
    public = os.environ.get("PUBLIC")
    if public:
        desktop_dirs.append(os.path.join(public, "Desktop"))

    candidates = []
    seen = set()
    for d in desktop_dirs:
        if not d or d in seen or not os.path.isdir(d):
            continue
        seen.add(d)
        for name in os.listdir(d):
            if name.lower().endswith(".lnk"):
                low = name.lower()
                if any(k.lower() in low for k in GAME_SHORTCUT_KEYWORDS):
                    candidates.append(os.path.join(d, name))
    return candidates


def read_game_shortcut(lnk_path):
    """通过 PowerShell 的 WScript.Shell 读取 .lnk 的目标路径、参数、工作目录。"""
    ps = (
        "$WshShell = New-Object -ComObject WScript.Shell;"
        "$s = $WshShell.CreateShortcut('" + lnk_path.replace("'", "''") + "');"
        "Write-Output ('TARGET=' + $s.TargetPath);"
        "Write-Output ('ARGS=' + $s.Arguments);"
        "Write-Output ('WORKDIR=' + $s.WorkingDirectory);"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
    )
    target, args, workdir = "", "", ""
    for line in proc.stdout.splitlines():
        if line.startswith("TARGET="):
            target = line[len("TARGET="):].strip()
        elif line.startswith("ARGS="):
            args = line[len("ARGS="):].strip()
        elif line.startswith("WORKDIR="):
            workdir = line[len("WORKDIR="):].strip()
    return target, args, workdir


def launch_game_by_shortcut():
    """按桌面快捷方式参数启动游戏，返回 (是否成功, 说明)。"""
    candidates = find_game_shortcut()
    if not candidates:
        return False, "未找到桌面「剑与远征：启程」快捷方式，无法自动启动游戏"
    lnk = candidates[0]
    target, args, workdir = read_game_shortcut(lnk)
    # 优先用快捷方式目标直接启动（普通 exe 快捷方式）
    if target and not target.lower().startswith("shell:appsfolder"):
        cmd = [target] + (shlex.split(args) if args else [])
        try:
            subprocess.Popen(cmd, cwd=workdir or None)
            return True, f"已按快捷方式启动游戏: {target}"
        except Exception:
            # UWP / 微信小游戏等目标无法直接 Popen，回退到下方系统打开
            pass
    # 回退：交给 Windows 外壳解析 .lnk（兼容 UWP / WeGame / 应用商店版本）
    try:
        os.startfile(lnk)
        return True, f"已通过快捷方式启动游戏: {lnk}"
    except Exception as e:
        return False, f"启动游戏失败: {e}"


# 游戏窗口标题匹配关键字（窗口标题为「剑与远征：启程」）
GAME_WINDOW_KEYWORDS = ("剑与远征：启程", "剑与远征", "启程", "AFK Journey", "AFK")


def _find_game_window():
    """返回游戏窗口的 HWND，未找到返回 None。"""
    try:
        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def enum_cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if title and any(k in title for k in GAME_WINDOW_KEYWORDS):
                found.append(hwnd)
                return False
            return True

        user32.EnumWindows(enum_cb, 0)
        return found[0] if found else None
    except Exception:
        return None


def is_game_running():
    """判断游戏是否已在运行（存在可见的游戏窗口）。"""
    return _find_game_window() is not None


def focus_game_window():
    """将游戏窗口切换到前台（脚本启动前需确保游戏可见，否则模板匹配会失效）。"""
    try:
        hwnd = _find_game_window()
        if hwnd is None:
            return False, "未找到游戏窗口，无法置于前台（请先启动游戏）"
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        # 先恢复（若最小化），再置顶前台
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True, "已将游戏窗口切换到前台"
    except Exception as e:
        return False, f"聚焦游戏窗口失败: {e}"
