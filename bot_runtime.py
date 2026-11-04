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
import threading
import time
from ctypes import wintypes

import log_format
from common import get_work_path


class _StdoutTee:
    """把 stdout 同时输出到原始 stdout 与面板日志汇聚回调，
    使各子脚本中的 print(...) 调试日志也能显示在应用内「运行日志」面板。

    面板与文件都写**同一份整理后的行**：以前面板收的是逐次 write 的碎片（print 会分
    正文和换行两次调用），文件收的是带时间戳的整行，两边看到的东西不一样。现在统一
    按行缓冲，凑齐一行再同时送面板和文件，面板也因此不会再出现半行。
    """
    def __init__(self, sink):
        self._sink = sink
        self._orig = sys.__stdout__
        self._pending = ""

    def write(self, s):
        with contextlib.suppress(Exception):
            self._orig.write(s)  # type: ignore[union-attr]
        # 落盘必须带时刻：子脚本的 print 以前整段没有时间戳，调试时分不清
        # 「识别失败 12 次」是同一秒的抖动还是跨了半分钟。print 会分两次调用
        # （正文 + 换行），所以按行缓冲，凑齐一行才写一条，避免半行带时间戳。
        self._pending += s
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            body = log_format.format_body(line)
            if not body:
                continue
            stamp = time.strftime("%H:%M:%S")
            # 面板那一路由 _drain_log_queue 统一加时间戳，这里只送正文，否则会成双时间戳
            with contextlib.suppress(Exception):
                self._sink(body)
            append_log_file(f"[{stamp}] {body}\n")

    def flush(self):
        with contextlib.suppress(Exception):
            self._orig.flush()  # type: ignore[union-attr]


# 启动早期（GUI 实例创建前）的 stdout 缓冲：窗口模式下 sys.stdout 初始为 None，
# 必须尽早接管 stdout，否则启动期 print 会写入 None 而崩溃。
_early_stdout_buffer = []
def _early_stdout_sink(msg):
    _early_stdout_buffer.append(msg)


CONFIG_FILE = get_work_path("game_bot_config.json")

# 本地持久化日志文件：GUI 运行日志与控制台输出都会写入此文件，便于查看与反馈问题
LOG_FILE = get_work_path("game_bot.log")

# 文件写入失败回调（由 GUI 在启动时注册，弹窗提示用户把程序移到可写目录）
_FILE_WRITE_ERROR_CALLBACK = None
_log_file_lock = threading.Lock()


def set_file_write_error_callback(callback):
    """注册文件写入失败回调（GUI 启动时调用）。"""
    global _FILE_WRITE_ERROR_CALLBACK
    _FILE_WRITE_ERROR_CALLBACK = callback


def _notify_file_write_error(path):
    if _FILE_WRITE_ERROR_CALLBACK is not None:
        _FILE_WRITE_ERROR_CALLBACK(path)


MAX_LOG_BYTES = 5 * 1024 * 1024   # 单个日志文件上限；超限后滚动为 .1，避免长期运行无限膨胀


def _rotate_log_if_needed():
    """日志超过上限时把 LogFile 改名成 .1（覆盖旧备份），再让调用方新建。

    只保留一份备份：这类日志主要用来看"最近发生了什么"，留太多份既占空间又难翻。
    """
    try:
        if os.path.getsize(LOG_FILE) < MAX_LOG_BYTES:
            return
        backup = LOG_FILE + ".1"
        if os.path.exists(backup):
            os.remove(backup)
        os.rename(LOG_FILE, backup)
    except OSError:
        pass   # 拿不到大小 / 改名失败（文件被占用等）就不轮转，保证日志照常写入


def append_log_file(text):
    """将文本追加到本地持久化日志文件；写入失败仅通知回调，不抛异常。"""
    if not text:
        return
    try:
        with _log_file_lock:
            _rotate_log_if_needed()
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(text)
    except Exception:
        _notify_file_write_error(LOG_FILE)


class _PersistentStdout:
    """同时保留控制台输出和写入本地日志文件（用于 GUI 实例创建前的早期阶段）。"""

    def __init__(self, stream, path):
        self.stream = stream
        self.path = path

    def write(self, text):
        if not text:
            return 0
        try:
            self.stream.write(text)
            self.stream.flush()
        except Exception:
            # 打包后的 GUI 程序可能没有可用控制台，忽略控制台输出失败。
            pass
        append_log_file(text)
        return len(text)

    def flush(self):
        with contextlib.suppress(Exception):
            self.stream.flush()


def _enable_persistent_console_log():
    if not isinstance(sys.stdout, _PersistentStdout):
        sys.stdout = _PersistentStdout(sys.stdout, LOG_FILE)


_enable_persistent_console_log()


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
    def __init__(self, name, enabled=False, params=None):
        self.name = name
        self.enabled = enabled
        self.params = params or {}
        self.status = "就绪"
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
