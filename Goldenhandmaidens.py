"""梅林初号机：AFK Journey（剑与远征：启程）日常任务自动化 GUI 主程序。

职责概览：
- 提供 tkinter 界面，勾选/配置每日任务并一键运行。
- 单一「开始运行 (F8) / 停止运行 (F9)」总开关，避免多停止按钮的混乱。
- 支持「立即开始」（启动游戏 + 运行脚本）与「定时开始」（每天循环，触发时
  自动检测游戏是否已运行，已运行则直接运行脚本）。
- 通过全局热键 F8/F9 控制运行；所有设置持久化到 game_bot_config.json。
- 脚本运行前自动将游戏窗口切换到前台（模板匹配依赖前台截图）。

主要分区（见下方 # ===== 分区注释 =====）：
- 路径与配置初始化（_ensure_config_files / load_config / save_config）
- GUI 构建（create_* 系列方法）
- 运行控制（update_master_button / start_all / stop_all）
- 定时开始（set_schedule / _schedule_loop / _fire_schedule）
- 全局热键（_register_hotkeys）
- 运行循环（run_scripts_thread）
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import os
import sys
import subprocess
import shlex
from datetime import datetime, timedelta
from version import __version__
import updater
from warehouse import ALL_HERO_NAMES, WAREHOUSE_TXT_PATH
from hero_metadata import HERO_RACE, HERO_JOB, RACE_NAMES, JOB_NAMES, PUSH_COMMON_HEROES, HERO_CN_NAMES
import ctypes
from ctypes import wintypes

def get_resource_path(relative_path):
    """获取资源文件的绝对路径，兼容打包后的exe"""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)

def get_work_path(relative_path):
    """获取工作目录下的文件路径（配置文件等）"""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)

CONFIG_FILE = get_work_path("game_bot_config.json")

def load_config():
    """加载配置文件"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
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
        self.last_run_time = None  # 最后执行时间

def _ensure_config_files():
    """首次运行时创建必要目录、从打包资源中复制配置文件到 exe 同目录"""
    # 确保 shared 目录存在
    shared_dir = get_work_path("shared")
    os.makedirs(shared_dir, exist_ok=True)

    config_files = []
    for fname in config_files:
        target = get_work_path(fname)
        if not os.path.exists(target):
            try:
                source = get_resource_path(fname)
                if os.path.exists(source):
                    import shutil
                    shutil.copy2(source, target)
            except Exception:
                pass


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


class GameBotGUI:
    def __init__(self, root):
        _ensure_config_files()
        self.root = root
        self.root.title("梅林初号机")
        self.root.geometry("1200x880")
        self.root.minsize(1024, 640)
        
        # 全局默认字体
        style = ttk.Style()
        style.configure(".", font=("Microsoft YaHei", 9))

        self.is_running = False
        self.current_script_index = 0
        self.stop_event = threading.Event()
        self._hotkey_lib = None

        # 日志：先建缓冲，setup_ui 中创建可见日志框后再冲刷
        self.log_text = None
        self._log_buffer = []

        # 加载配置
        self.config = load_config()
        self.auto_start_on_launch = self.config.get("auto_start_on_launch", False)
        self.auto_start_var = tk.BooleanVar(value=self.auto_start_on_launch)
        self.launch_game_on_open = self.config.get("launch_game_on_open", False)
        self.launch_game_var = tk.BooleanVar(value=self.launch_game_on_open)
        self.game_launch_delay = self.config.get("game_launch_delay", 20)
        self.game_wait_var = tk.IntVar(value=self.game_launch_delay)
        self.is_first_run = not self.config.get("first_run_completed", False)

        # 定时开始（每天循环）：存储为 "HH:MM" 或 None
        self.schedule_time = self.config.get("schedule_time", None)
        self.schedule_hour_var = tk.IntVar(value=8)
        self.schedule_min_var = tk.IntVar(value=0)
        self.schedule_active = False
        self.scheduled_time = None
        self.schedule_cancel_event = threading.Event()
        
        self.scripts = [
            ScriptConfig("登录", enabled=True),
            ScriptConfig("仓库管理", enabled=True),
            ScriptConfig("邮件", enabled=False, daily_reset=True),
            ScriptConfig("好友奖励", enabled=False, daily_reset=True),
            ScriptConfig("普竞", enabled=False),
            ScriptConfig("迷梦之域", enabled=False, params={"challenge_count": 5}),
            ScriptConfig("女神塔", enabled=False),
            ScriptConfig("挂机奖励", enabled=False, params={"paid_times": 0}, daily_reset=True),
            ScriptConfig("商城", enabled=False, daily_reset=True),
            ScriptConfig("日常任务", enabled=False, daily_reset=True),
            ScriptConfig("爬塔", enabled=False),
            ScriptConfig("幻灵推图", enabled=False),
            ScriptConfig("推图", enabled=False),
            ScriptConfig("循环推图", enabled=False),
            ScriptConfig("异界迷宫", enabled=False, params={
                "challenges": 1,
                "floors": "15",
                "formation_name": "",
                "shenceng_formation_name": ""
            }),
        ]
        
        # 从配置中加载脚本状态
        for script in self.scripts:
            script_config = self.config.get("scripts", {}).get(script.name, {})
            script.enabled = script_config.get("enabled", script.enabled)
            script.params = script_config.get("params", script.params)
            script.daily_reset = script_config.get("daily_reset", script.daily_reset)
            script.last_run_time = script_config.get("last_run_time", None)
        
        self.setup_ui()

        # 若配置了定时开始，自动重新设定（按每天循环）
        if self.config.get("schedule_time"):
            try:
                hh, mm = map(int, str(self.config["schedule_time"]).split(":"))
                self.schedule_hour_var.set(hh)
                self.schedule_min_var.set(mm)
                self.set_schedule()
            except Exception:
                pass

        # 注册全局热键 F8=开始运行 F9=停止运行
        self._register_hotkeys()

        # 启动后自动流程：可选启动游戏 + 可选自动运行脚本
        if self.launch_game_on_open or self.auto_start_on_launch:
            self.root.after(1500, self._auto_open_flow)

        # 启动后自动检查更新（后台线程，不阻塞界面）
        self.root.after(1000, self._auto_check_update)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=0)
        
        self.create_control_bar(main_frame)
        self.create_dashboard(main_frame)
        self.create_script_panel(main_frame)
        self.create_log_panel(main_frame)
        
    def create_control_bar(self, parent):
        control_frame = ttk.Frame(parent, padding="10")
        control_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 第一行：主要操作
        top_frame = ttk.Frame(control_frame)
        top_frame.pack(fill=tk.X)

        self.master_switch_btn = ttk.Button(
            top_frame,
            text="开始运行 (F8)",
            command=self.toggle_master_switch
        )
        self.master_switch_btn.pack(side=tk.LEFT, padx=5)

        self.immediate_btn = ttk.Button(
            top_frame, text="立即开始", command=self.launch_game_then_start
        )
        self.immediate_btn.pack(side=tk.LEFT, padx=5)

        self.hotkey_hint = ttk.Label(
            top_frame, text="F8 开始 / F9 停止", foreground="gray"
        )
        self.hotkey_hint.pack(side=tk.LEFT, padx=10)

        self.version_label = ttk.Label(top_frame, text=__version__, foreground="gray")
        self.version_label.pack(side=tk.RIGHT, padx=5)

        self.help_btn = ttk.Button(
            control_frame,
            text="帮助",
            command=self.show_help_window
        )
        self.help_btn.pack(side=tk.LEFT, padx=5)

        self.sponsor_btn = ttk.Button(
            control_frame,
            text="赞助",
            command=self.show_sponsor
        )
        self.sponsor_btn.pack(side=tk.LEFT, padx=5)

        self.update_btn = ttk.Button(
            top_frame, text="检查更新", command=self._check_update_clicked
        )
        self.update_btn.pack(side=tk.RIGHT, padx=5)

        # 第二行：选项 + 定时开始
        opt_frame = ttk.Frame(control_frame)
        opt_frame.pack(fill=tk.X, pady=(8, 0))

        self.auto_start_check = ttk.Checkbutton(
            opt_frame,
            text="启动后自动运行",
            variable=self.auto_start_var,
            command=self.on_auto_start_changed
        )
        self.auto_start_check.pack(side=tk.LEFT, padx=5)

        self.launch_game_check = ttk.Checkbutton(
            opt_frame,
            text="启动时启动游戏",
            variable=self.launch_game_var,
            command=self.on_launch_game_changed
        )
        self.launch_game_check.pack(side=tk.LEFT, padx=5)

        ttk.Label(opt_frame, text="游戏等待(s)").pack(side=tk.LEFT, padx=(10, 0))
        self.game_wait_spin = ttk.Spinbox(
            opt_frame,
            from_=0, to=120, width=4,
            textvariable=self.game_wait_var,
            command=self.on_game_wait_changed
        )
        self.game_wait_spin.pack(side=tk.LEFT, padx=2)
        # 手动输入（不仅是点击箭头）也要保存
        self.game_wait_spin.bind("<KeyRelease>", lambda e: self.on_game_wait_changed())
        self.game_wait_spin.bind("<FocusOut>", lambda e: self._sync_game_wait_spin())

        ttk.Label(opt_frame, text="  定时开始:").pack(side=tk.LEFT, padx=(10, 2))
        self.sched_hour_spin = ttk.Spinbox(
            opt_frame, from_=0, to=23, width=3,
            textvariable=self.schedule_hour_var
        )
        self.sched_hour_spin.pack(side=tk.LEFT, padx=1)
        ttk.Label(opt_frame, text="时").pack(side=tk.LEFT)
        self.sched_min_spin = ttk.Spinbox(
            opt_frame, from_=0, to=59, width=3,
            textvariable=self.schedule_min_var
        )
        self.sched_min_spin.pack(side=tk.LEFT, padx=1)
        ttk.Label(opt_frame, text="分").pack(side=tk.LEFT, padx=(0, 6))

        self.sched_set_btn = ttk.Button(
            opt_frame, text="设定定时", command=self.set_schedule
        )
        self.sched_set_btn.pack(side=tk.LEFT, padx=3)
        self.sched_cancel_btn = ttk.Button(
            opt_frame, text="取消定时", command=self.cancel_schedule, state=tk.DISABLED
        )
        self.sched_cancel_btn.pack(side=tk.LEFT, padx=3)

        self.schedule_status_label = ttk.Label(opt_frame, text="未设定定时", foreground="blue")
        self.schedule_status_label.pack(side=tk.LEFT, padx=10)

    def create_dashboard(self, parent):
        dashboard_frame = ttk.LabelFrame(parent, text="功能", padding="10")
        dashboard_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        
        # 添加滚动条
        canvas = tk.Canvas(dashboard_frame, width=150, height=300)
        scrollbar = ttk.Scrollbar(dashboard_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.script_buttons = []
        for i, script in enumerate(self.scripts):
            btn = ttk.Button(
                scrollable_frame,
                text=script.name,
                width=15,
                command=lambda idx=i: self.select_script(idx)
            )
            btn.pack(pady=5, fill=tk.X)
            self.script_buttons.append(btn)
            
        self.update_dashboard_buttons()
        
    def create_script_panel(self, parent):
        self.script_panel = ttk.LabelFrame(parent, text="配置", padding="10")
        self.script_panel.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.script_panel.columnconfigure(1, weight=1)
        
        self.script_name_label = ttk.Label(self.script_panel, text="", font=("Microsoft YaHei", 12, "bold"))
        self.script_name_label.grid(row=0, column=0, columnspan=2, pady=(0, 10))
        
        self.script_enabled_var = tk.BooleanVar()
        self.script_enabled_check = ttk.Checkbutton(
            self.script_panel,
            text="开启",
            variable=self.script_enabled_var,
            command=self.on_script_enabled_changed
        )
        self.script_enabled_check.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        self.param_frame = ttk.Frame(self.script_panel)
        self.param_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.update_script_panel()
        
    def create_log_panel(self, parent):
        log_frame = ttk.LabelFrame(parent, text="运行日志", padding="10")
        log_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        text = tk.Text(log_frame, wrap=tk.WORD, height=10, state=tk.DISABLED)
        text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        text.configure(yscrollcommand=scrollbar.set)

        self.log_text = text

        # 冲刷早期缓冲日志（setup_ui 之前产生的日志）
        for line in getattr(self, '_log_buffer', []):
            text.configure(state=tk.NORMAL)
            text.insert(tk.END, line)
            text.configure(state=tk.DISABLED)
        self._log_buffer = []
        text.see(tk.END)
        
    def show_log_window(self):
        log_window = tk.Toplevel(self.root)
        log_window.title("任务日志")
        log_window.geometry("800x600")
        
        log_frame = ttk.Frame(log_window, padding="10")
        log_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        log_window.columnconfigure(0, weight=1)
        log_window.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        log_text = tk.Text(log_frame, wrap=tk.WORD)
        log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log_text.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        log_text.configure(yscrollcommand=scrollbar.set)
        
        # 复制当前日志内容
        log_text.insert(tk.END, self.log_text.get("1.0", tk.END))
        log_text.see(tk.END)

    def show_help_window(self):
        help_window = tk.Toplevel(self.root)
        help_window.title("帮助")
        help_window.geometry("700x650")

        readme_path = get_resource_path("README.md")
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = "README.md 未找到。"

        text_frame = ttk.Frame(help_window, padding="10")
        text_frame.pack(fill=tk.BOTH, expand=True)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=("Microsoft YaHei", 10),
                              padx=10, pady=10, borderwidth=0)
        text_widget.insert(tk.END, content)
        text_widget.configure(state=tk.DISABLED)

        text_scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=text_scrollbar.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def show_sponsor(self):
        qr_path = get_resource_path("sponsor_qrcode.png")
        if os.path.exists(qr_path):
            os.startfile(qr_path)
        else:
            messagebox.showinfo("赞助", "赞助二维码图片未找到。")

    def update_dashboard_buttons(self):
        for i, (btn, script) in enumerate(zip(self.script_buttons, self.scripts)):
            if i == self.current_script_index:
                btn.state(['pressed'])
            else:
                btn.state(['!pressed'])
            
            if script.enabled:
                btn.configure(text=f"✓ {script.name}")
            else:
                btn.configure(text=script.name)
                
    def update_script_panel(self):
        script = self.scripts[self.current_script_index]
        self.script_name_label.configure(text=script.name)
        self.script_enabled_var.set(script.enabled)

        # 缓存仓库面板，避免切换时重建 472 个 widget 导致卡顿
        wh_container = getattr(self, '_warehouse_container', None)
        if wh_container is not None:
            wh_container.grid_remove()

        for widget in list(self.param_frame.winfo_children()):
            if widget is wh_container:
                continue
            widget.destroy()

        if script.name == "迷梦之域":
            self.create_mimengzhiyu_params(script, 0)
        elif script.name == "挂机奖励":
            self.create_shouquguajijiangli_params(script, 0)
        elif script.name == "异界迷宫":
            self.create_yijiemigong_params(script, 0)
        elif script.name in ("幻灵推图", "推图", "循环推图"):
            self.create_push_params(0)
        elif script.name == "仓库管理":
            self.create_warehouse_params(0)
            
    def create_mimengzhiyu_params(self, script, row=0):
        ttk.Label(self.param_frame, text="挑战次数:").grid(row=row, column=0, sticky=tk.W, pady=2)
        
        challenge_count = script.params.get("challenge_count", 5)
        self.challenge_count_var = tk.IntVar(value=challenge_count)
        
        challenge_spinbox = ttk.Spinbox(
            self.param_frame,
            from_=1,
            to=100,
            textvariable=self.challenge_count_var,
            width=10
        )
        challenge_spinbox.grid(row=row, column=1, sticky=tk.W, pady=2)
        
        def on_param_change():
            script.params["challenge_count"] = self.challenge_count_var.get()
            self.save_config()
            
        challenge_spinbox.bind("<FocusOut>", lambda e: on_param_change())
        challenge_spinbox.bind("<Return>", lambda e: on_param_change())
        
    def create_pujing_params(self, script, row=0):
        ttk.Label(self.param_frame, text="暂无参数").grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        
    def create_push_params(self, row=0):
        push_settings = self.config.get("push_settings", {})

        # 跳过手动战斗
        skip_manual = push_settings.get("skip_manual", True)
        self.skip_manual_var = tk.BooleanVar(value=skip_manual)
        ttk.Checkbutton(
            self.param_frame,
            text="跳过手动战斗阵容",
            variable=self.skip_manual_var,
            command=self.on_push_param_change
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=2)
        row += 1

        # 失败重试次数
        ttk.Label(self.param_frame, text="失败重试次数 (1-3):").grid(row=row, column=0, sticky=tk.W, pady=2)
        retry_count = push_settings.get("retry_count", 3)
        self.retry_count_var = tk.IntVar(value=retry_count)
        ttk.Spinbox(
            self.param_frame,
            from_=1,
            to=3,
            textvariable=self.retry_count_var,
            width=5
        ).grid(row=row, column=1, sticky=tk.W, pady=2)
        row += 1

        # Spinbox 的绑定
        for child in self.param_frame.winfo_children():
            if isinstance(child, ttk.Spinbox):
                child.bind("<FocusOut>", lambda e: self.on_push_param_change())
                child.bind("<Return>", lambda e: self.on_push_param_change())

        ttk.Label(self.param_frame, text="注: 幻灵推图、推图、循环推图共享此设置").grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=5)

    def on_push_param_change(self):
        self.config["push_settings"] = {
            "skip_manual": self.skip_manual_var.get(),
            "retry_count": self.retry_count_var.get(),
        }
        self.save_config()
        
    def create_warehouse_params(self, row=0):
        """仓库管理：种族+职业筛选，手动勾选英雄练度（首次创建后缓存，切换不重建）"""
        wh_container = getattr(self, '_warehouse_container', None)
        if wh_container is not None:
            wh_container.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
            return

        LEVELS = ["未拥有", "低", "高"]
        LEVEL_LABELS = {"未拥有": "未拥有", "低": "不到巅峰+", "高": "巅峰+及以上"}

        # 从 warehouse_heroes.txt 加载已有数据
        hero_levels = {}
        if os.path.exists(WAREHOUSE_TXT_PATH):
            with open(WAREHOUSE_TXT_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if ',' in line:
                        name, lvl = line.split(',', 1)
                        hero_levels[name.strip()] = lvl.strip()

        self._hero_levels = hero_levels

        # 外层容器，用于缓存
        container = ttk.Frame(self.param_frame)
        container.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        container.columnconfigure(0, weight=1)
        self._warehouse_container = container

        # === 筛选行 ===
        filter_frame = ttk.Frame(container)
        filter_frame.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))

        ttk.Label(filter_frame, text="种族:").pack(side=tk.LEFT, padx=(0, 2))
        race_values = ["全部"] + list(RACE_NAMES.values())
        self._race_filter_var = tk.StringVar(value="全部")
        race_combo = ttk.Combobox(filter_frame, textvariable=self._race_filter_var,
                                  values=race_values, state="readonly", width=8)
        race_combo.pack(side=tk.LEFT, padx=(0, 10))
        race_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_hero_filter())

        ttk.Label(filter_frame, text="职业:").pack(side=tk.LEFT, padx=(0, 2))
        job_values = ["全部"] + list(JOB_NAMES.values())
        self._job_filter_var = tk.StringVar(value="全部")
        job_combo = ttk.Combobox(filter_frame, textvariable=self._job_filter_var,
                                 values=job_values, state="readonly", width=8)
        job_combo.pack(side=tk.LEFT, padx=(0, 10))
        job_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_hero_filter())

        # 仅显示常用
        self._common_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_frame, text="仅常用", variable=self._common_only_var,
                        command=self._apply_hero_filter).pack(side=tk.LEFT, padx=(0, 10))

        # 批量设置按钮
        for level in LEVELS:
            ttk.Button(filter_frame, text=f"全部→{LEVEL_LABELS[level]}",
                       command=lambda l=level: self._set_all_hero_levels(l)).pack(side=tk.LEFT, padx=2)

        # === 可滚动英雄列表 ===
        canvas = tk.Canvas(container, width=550, height=400, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        self._hero_list_frame = ttk.Frame(canvas)

        self._hero_list_frame.bind("<Configure>",
                                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._hero_list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        canvas.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=1, column=2, sticky=(tk.N, tk.S))

        container.rowconfigure(1, weight=1)

        # 为每个英雄创建一行：名字 + 3 个 Radiobutton
        self._hero_vars = {}   # hero_name → tk.StringVar
        self._hero_rows = {}   # hero_name → ttk.Frame (整行)

        for i, hero_name in enumerate(ALL_HERO_NAMES):
            level = hero_levels.get(hero_name, "高")
            var = tk.StringVar(value=level)
            self._hero_vars[hero_name] = var

            row_frame = ttk.Frame(self._hero_list_frame)
            row_frame.grid(row=i, column=0, sticky=tk.W, pady=0)

            ttk.Label(row_frame, text=HERO_CN_NAMES.get(hero_name, hero_name), width=8, anchor=tk.W).pack(side=tk.LEFT, padx=(0, 5))
            for lvl in LEVELS:
                ttk.Radiobutton(row_frame, text=LEVEL_LABELS[lvl], variable=var, value=lvl,
                                command=lambda n=hero_name: self._on_hero_level_change(n)
                                ).pack(side=tk.LEFT, padx=2)

            self._hero_rows[hero_name] = row_frame

        # 种族/职业查找表，供筛选用
        self._hero_race = {}
        self._hero_job = {}
        for hero_name in ALL_HERO_NAMES:
            race_key = HERO_RACE.get(hero_name, "")
            job_key = HERO_JOB.get(hero_name, "")
            self._hero_race[hero_name] = RACE_NAMES.get(race_key, "")
            self._hero_job[hero_name] = JOB_NAMES.get(job_key, "")

        self._apply_hero_filter()

    def _apply_hero_filter(self):
        """根据种族/职业/常用筛选条件显示/隐藏英雄行"""
        race_filter = self._race_filter_var.get()
        job_filter = self._job_filter_var.get()
        common_only = self._common_only_var.get()

        for hero_name, row_frame in self._hero_rows.items():
            if common_only and hero_name not in PUSH_COMMON_HEROES:
                row_frame.grid_remove()
                continue
            match_race = (race_filter == "全部" or self._hero_race.get(hero_name, "") == race_filter)
            match_job = (job_filter == "全部" or self._hero_job.get(hero_name, "") == job_filter)
            if match_race and match_job:
                row_frame.grid()
            else:
                row_frame.grid_remove()

    def _on_hero_level_change(self, hero_name):
        """Radiobutton 切换时自动写入文件"""
        self._hero_levels[hero_name] = self._hero_vars[hero_name].get()
        self._write_warehouse_txt()

    def _set_all_hero_levels(self, level):
        """批量设置所有英雄为指定练度"""
        for hero_name in ALL_HERO_NAMES:
            self._hero_levels[hero_name] = level
            if hero_name in self._hero_vars:
                self._hero_vars[hero_name].set(level)
        self._write_warehouse_txt()

    def _write_warehouse_txt(self):
        """将当前英雄练度写入 warehouse_heroes.txt"""
        hero_levels = getattr(self, '_hero_levels', {})
        try:
            with open(WAREHOUSE_TXT_PATH, 'w', encoding='utf-8') as f:
                for hero_name in ALL_HERO_NAMES:
                    level = hero_levels.get(hero_name, "高")
                    f.write(f"{hero_name},{level}\n")
        except Exception as e:
            self.log(f"写入仓库文件失败: {str(e)}")
    
    def create_shouquguajijiangli_params(self, script, row=0):
        ttk.Label(self.param_frame, text="付费购买次数 (0-2):").grid(row=row, column=0, sticky=tk.W, pady=2)
        
        paid_times = script.params.get("paid_times", 0)
        self.paid_times_var = tk.IntVar(value=paid_times)
        
        paid_times_spinbox = ttk.Spinbox(
            self.param_frame,
            from_=0,
            to=2,
            textvariable=self.paid_times_var,
            width=10
        )
        paid_times_spinbox.grid(row=row, column=1, sticky=tk.W, pady=2)
        
        def on_param_change():
            script.params["paid_times"] = self.paid_times_var.get()
            self.save_config()
            
        paid_times_spinbox.bind("<FocusOut>", lambda e: on_param_change())
        paid_times_spinbox.bind("<Return>", lambda e: on_param_change())
        
        ttk.Label(self.param_frame, text="注: 免费三次默认购买掉").grid(row=row+1, column=0, columnspan=2, sticky=tk.W, pady=5)

    def create_yijiemigong_params(self, script, row=0):
        # 加载 formations.json 获取阵容列表（从 EXE 资源读取）
        formations = {}
        try:
            with open(get_resource_path("formations.json"), "r", encoding="utf-8") as f:
                formations = json.load(f)
        except Exception:
            pass
        all_forms = list(formations.keys())

        # 挑战次数
        ttk.Label(self.param_frame, text="挑战次数:").grid(row=row, column=0, sticky=tk.W, pady=2)
        challenges = script.params.get("challenges", 1)
        self.mg_challenges_var = tk.IntVar(value=challenges)
        ttk.Spinbox(self.param_frame, from_=1, to=100, textvariable=self.mg_challenges_var,
                    width=10).grid(row=row, column=1, sticky=tk.W, pady=2)
        row += 1

        # 层数选择（互斥）
        ttk.Label(self.param_frame, text="层数:").grid(row=row, column=0, sticky=tk.W, pady=2)
        floors = script.params.get("floors", "15")
        self.mg_floors_var = tk.StringVar(value=floors)
        floor_frame = ttk.Frame(self.param_frame)
        floor_frame.grid(row=row, column=1, sticky=tk.W, pady=2)
        ttk.Radiobutton(floor_frame, text="15层", variable=self.mg_floors_var, value="15").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(floor_frame, text="20层", variable=self.mg_floors_var, value="20").pack(side=tk.LEFT, padx=5)
        row += 1

        # 初始阵容（下拉列表，不含括号）
        ttk.Label(self.param_frame, text="初始阵容:").grid(row=row, column=0, sticky=tk.W, pady=2)
        form_name = script.params.get("formation_name", "")
        self.mg_form_var = tk.StringVar(value=form_name if form_name in all_forms else "")
        form_combo = ttk.Combobox(self.param_frame, textvariable=self.mg_form_var,
                                  values=all_forms, state="readonly", width=35)
        form_combo.grid(row=row, column=1, sticky=tk.W, pady=2)
        if all_forms and not self.mg_form_var.get():
            form_combo.set(all_forms[0])
        row += 1

        # 20层boss阵容（下拉列表，含括号）
        ttk.Label(self.param_frame, text="20层boss阵容:").grid(row=row, column=0, sticky=tk.W, pady=2)
        shenceng_name = script.params.get("shenceng_formation_name", "")
        self.mg_shenceng_var = tk.StringVar(value=shenceng_name if shenceng_name in all_forms else "")
        shenceng_combo = ttk.Combobox(self.param_frame, textvariable=self.mg_shenceng_var,
                                      values=all_forms, state="readonly", width=35)
        shenceng_combo.grid(row=row, column=1, sticky=tk.W, pady=2)
        if all_forms and not self.mg_shenceng_var.get():
            shenceng_combo.set(all_forms[0])
        row += 1

        # 保存回调
        def on_param_change(*args):
            script.params["challenges"] = self.mg_challenges_var.get()
            script.params["floors"] = self.mg_floors_var.get()
            script.params["formation_name"] = self.mg_form_var.get()
            script.params["shenceng_formation_name"] = self.mg_shenceng_var.get()
            self.save_config()

        self.mg_challenges_var.trace_add("write", on_param_change)
        self.mg_floors_var.trace_add("write", on_param_change)
        self.mg_form_var.trace_add("write", on_param_change)
        self.mg_shenceng_var.trace_add("write", on_param_change)
        
    def select_script(self, index):
        self.current_script_index = index
        self.update_dashboard_buttons()
        self.update_script_panel()
        
    def on_script_enabled_changed(self):
        script = self.scripts[self.current_script_index]
        script.enabled = self.script_enabled_var.get()
        self.save_config()
        self.update_dashboard_buttons()
        
    def on_auto_start_changed(self):
        self.auto_start_on_launch = self.auto_start_var.get()
        self.save_config()

    def on_launch_game_changed(self):
        self.launch_game_on_open = self.launch_game_var.get()
        self.save_config()

    def on_game_wait_changed(self):
        try:
            val = int(self.game_wait_var.get())
        except (ValueError, TypeError):
            return
        val = max(0, min(120, val))
        self.game_launch_delay = val
        self.save_config()

    def _sync_game_wait_spin(self):
        """失焦时把手动输入的值收敛到合法范围并保存。"""
        try:
            val = int(self.game_wait_var.get())
        except (ValueError, TypeError):
            val = self.game_launch_delay
        val = max(0, min(120, val))
        self.game_wait_var.set(val)
        self.game_launch_delay = val
        self.save_config()

    def toggle_master_switch(self):
        if self.is_running:
            self.stop_all()
        else:
            self.start_all()

    # ===== 运行控制（开始 / 停止 / 主按钮） =====
    def update_master_button(self):
        if self.is_running:
            self.master_switch_btn.configure(text="停止运行 (F9)")
        else:
            self.master_switch_btn.configure(text="开始运行 (F8)")

    def start_all(self):
        self.is_running = True
        self.stop_event.clear()
        self.update_master_button()
        
        # 检查是否有脚本启用
        enabled_scripts = [s for s in self.scripts if s.enabled]
        if not enabled_scripts:
            messagebox.showwarning("警告", "没有启用任何脚本！")
            self.stop_all()
            return
            
        self.log(f"开始运行脚本")
        
        for script in self.scripts:
            script.status = "等待中"
        self.update_script_panel()
        
        thread = threading.Thread(target=self.run_scripts_thread, args=(enabled_scripts,))
        thread.daemon = True
        thread.start()
        
    def stop_all(self):
        self.stop_event.set()
        self.is_running = False
        self.update_master_button()
        
        for script in self.scripts:
            if script.status == "运行中":
                script.status = "已停止"
        self.update_script_panel()
        
        self.log("所有脚本已停止")
        
    def on_closing(self):
        import subprocess
        self._unregister_hotkeys()
        if self.is_running:
            if messagebox.askokcancel("退出", "脚本正在运行中，确定要停止并退出吗？"):
                self.stop_all()
                subprocess.run(["taskkill", "/F", "/IM", "click_from_file.exe"], capture_output=True)
                self.root.destroy()
        else:
            subprocess.run(["taskkill", "/F", "/IM", "click_from_file.exe"], capture_output=True)
            self.root.destroy()
        
    def launch_game_then_start(self, launch_game=True):
        """启动游戏（可选），等待指定秒数后开始运行脚本流程。"""
        if self.is_running:
            self.log("脚本已在运行中，忽略本次启动请求")
            return
        enabled = [s for s in self.scripts if s.enabled]
        if not enabled:
            messagebox.showwarning("警告", "没有启用任何脚本！")
            return
        if launch_game:
            self.launch_game_from_shortcut()
            delay = self.game_launch_delay
        else:
            delay = 0
        self.log(f"{delay} 秒后将开始运行脚本流程")
        # 等待后先确保游戏窗口在前台，再开始脚本（避免因游戏不在前台导致模板匹配失效）
        self.root.after(max(0, int(delay)) * 1000, self._start_after_focus)

    def _start_after_focus(self):
        ok, msg = focus_game_window()
        self.log(msg)
        self.start_all()

    def _auto_open_flow(self):
        """启动后自动流程：按需启动游戏，等待后再按需自动运行脚本。"""
        if self.launch_game_on_open or self.auto_start_on_launch:
            self.launch_game_then_start(launch_game=self.launch_game_on_open)
        else:
            self.log("未启用启动时自动流程")

    def launch_game_from_shortcut(self):
        ok, msg = launch_game_by_shortcut()
        self.log(msg)
        if ok:
            self.log(f"游戏启动命令已发送，将在 {self.game_launch_delay} 秒后自动开始脚本流程")
        return ok

    # ===== 定时开始（每天循环） =====
    def set_schedule(self):
        try:
            hh = int(self.schedule_hour_var.get())
            mm = int(self.schedule_min_var.get())
        except Exception:
            messagebox.showerror("错误", "请填写有效的小时和分钟")
            return
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            messagebox.showerror("错误", "时间超出范围 (时 0-23, 分 0-59)")
            return
        now = datetime.now()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
        self.scheduled_time = target
        self.schedule_time = f"{hh:02d}:{mm:02d}"
        self.schedule_active = True
        self.schedule_cancel_event.clear()
        self.save_config()
        self.log(f"已设定定时开始: {self.schedule_time}（{target.strftime('%Y-%m-%d %H:%M')}，每天循环）")
        threading.Thread(target=self._schedule_loop, daemon=True).start()
        self.update_schedule_status()

    def cancel_schedule(self):
        self.schedule_active = False
        self.schedule_cancel_event.set()
        self.scheduled_time = None
        self.schedule_time = None
        self.save_config()
        self._set_schedule_status("未设定定时")
        self.log("已取消定时开始")

    def _schedule_loop(self):
        while True:
            if not self.schedule_active or self.schedule_cancel_event.is_set():
                return
            remaining = (self.scheduled_time - datetime.now()).total_seconds()
            if remaining <= 0:
                self.root.after(0, self._fire_schedule)
                return
            self.root.after(0, self.update_schedule_status)
            self.schedule_cancel_event.wait(timeout=1.0)

    def _fire_schedule(self):
        self.schedule_active = False
        self.scheduled_time = None
        if self.is_running:
            self.log("定时开始：脚本已在运行中，跳过本次触发")
            self._set_schedule_status("未设定定时")
            return
        # 定时启动时先检查游戏是否已启动：已启动则直接开始脚本，避免重复拉起游戏
        if is_game_running():
            self.log("定时开始时间到，游戏已在运行，直接启动脚本")
            self.launch_game_then_start(launch_game=False)
        else:
            self.log("定时开始时间到，启动游戏并运行脚本")
            self.launch_game_then_start(launch_game=True)
        # 触发后继续按每天循环重新设定
        self.set_schedule()

    def update_schedule_status(self):
        if not self.schedule_active or self.scheduled_time is None:
            self._set_schedule_status("未设定定时")
            return
        remaining = int((self.scheduled_time - datetime.now()).total_seconds())
        if remaining < 0:
            remaining = 0
        h = remaining // 3600
        m = (remaining % 3600) // 60
        s = remaining % 60
        self._set_schedule_status(f"已定时 {self.schedule_time} 倒计时 {h:02d}:{m:02d}:{s:02d}")

    def _set_schedule_status(self, text):
        if hasattr(self, "schedule_status_label") and self.schedule_status_label is not None:
            self.schedule_status_label.configure(text=text)
        if hasattr(self, "sched_cancel_btn") and self.sched_cancel_btn is not None:
            if text.startswith("已定时"):
                self.sched_cancel_btn.configure(state=tk.NORMAL)
            else:
                self.sched_cancel_btn.configure(state=tk.DISABLED)

    # ===== 全局热键（F8 开始 / F9 停止） =====
    def _register_hotkeys(self):
        """注册全局热键：F8=开始运行，F9=停止运行。
        需要 keyboard 库才能在任意窗口聚焦时生效；否则回退为仅 GUI 聚焦时生效。"""
        try:
            import keyboard
            self._hk_start = keyboard.add_hotkey('f8', lambda: self.root.after(0, self._hotkey_start))
            self._hk_stop = keyboard.add_hotkey('f9', lambda: self.root.after(0, self._hotkey_stop))
            self._hotkey_lib = keyboard
            self.log("已注册全局热键 F8=开始运行 / F9=停止运行")
        except Exception as e:
            print(f"全局热键注册失败({e})，回退为窗口聚焦热键")
            self.root.bind_all('<KeyPress-F8>', lambda e: self._hotkey_start())
            self.root.bind_all('<KeyPress-F9>', lambda e: self._hotkey_stop())
            self._hotkey_lib = None

    def _unregister_hotkeys(self):
        if self._hotkey_lib is not None:
            try:
                self._hotkey_lib.remove_hotkey(self._hk_start)
                self._hotkey_lib.remove_hotkey(self._hk_stop)
            except Exception:
                pass

    def _hotkey_start(self):
        if not self.is_running:
            self.start_all()

    def _hotkey_stop(self):
        if self.is_running:
            self.stop_all()

    # ===== 运行循环（在线程内依次执行各脚本） =====
    def run_scripts_thread(self, scripts_to_run):
        # 先杀掉旧进程，再启动新的 click_from_file.exe（确保工作目录正确）
        import subprocess
        try:
            subprocess.run(["taskkill", "/F", "/IM", "click_from_file.exe"], capture_output=True)
            time.sleep(0.5)
        except Exception:
            pass

        self.log("运行click_from_file.exe...")
        try:
            ahk_exe_path = get_resource_path("click_from_file.exe")
            work_dir = get_work_path("")
            self.log(f"脚本路径: {ahk_exe_path}")
            self.log(f"工作目录: {work_dir}")

            if not os.path.exists(ahk_exe_path):
                self.log(f"错误: click_from_file.exe 文件不存在: {ahk_exe_path}")
            else:
                subprocess.Popen([ahk_exe_path, work_dir])
                self.log("click_from_file.exe 启动成功")
        except Exception as e:
            self.log(f"运行click_from_file.exe失败: {str(e)}")
            self.log("警告: click_from_file.exe 未启动，部分功能可能无法正常工作")
        
        time.sleep(2)
        
        # 顺序调用其他脚本
        script_order = [
            "登录", "仓库管理", "邮件", "好友奖励", "普竞", "迷梦之域", "女神塔", 
            "挂机奖励", "商城", "日常任务", "爬塔", "幻灵推图", "推图", "循环推图", "异界迷宫"
        ]
        
        for script_name in script_order:
            if self.stop_event.is_set():
                break
                
            script = next((s for s in self.scripts if s.name == script_name), None)
            if not script or not script.enabled:
                continue
                
            script.status = "运行中"
            self.root.after(0, self.update_script_panel)
            self.log(f"开始执行: {script.name}")
            
            try:
                # 检查是否需要停止
                if self.stop_event.is_set():
                    script.status = "已停止"
                    self.log(f"{script.name} 已停止")
                    result = False
                else:
                    if script.name == "登录":
                        try:
                            import start
                            start.main()
                            result = True
                        except ImportError as e:
                            self.log(f"登录模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "仓库管理":
                        try:
                            # 手动模式：直接写入 warehouse_heroes.txt
                            # 如果用户已在面板中勾选过，文件已是最新；否则生成默认文件
                            import warehouse
                            if not os.path.exists(WAREHOUSE_TXT_PATH):
                                self._write_warehouse_txt()
                            self.log("仓库英雄数据已就绪")
                            result = True
                        except ImportError as e:
                            self.log(f"仓库管理模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "邮件":
                        try:
                            import youjian
                            youjian.main()
                            result = True
                        except ImportError as e:
                            self.log(f"邮件模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "好友奖励":
                        try:
                            import haoyoujiangli
                            haoyoujiangli.main()
                            result = True
                        except ImportError as e:
                            self.log(f"好友奖励模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "普竞":
                        try:
                            import pujing
                            pujing.flow_pujing()
                            result = True
                        except ImportError as e:
                            self.log(f"普竞模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "迷梦之域":
                        try:
                            from mimengzhiyu import flow_mimengzhiyu
                            challenge_count = script.params.get("challenge_count")
                            result = flow_mimengzhiyu(challenge_count=challenge_count)
                        except ImportError as e:
                            self.log(f"迷梦之域模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "女神塔":
                        try:
                            import nvshenta
                            nvshenta.flow_nvshenta()
                            result = True
                        except ImportError as e:
                            self.log(f"女神塔模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "挂机奖励":
                        try:
                            import shouquguajijiangli
                            paid_times = script.params.get("paid_times", 0)
                            shouquguajijiangli.main(paid_times=paid_times)
                            result = True
                        except ImportError as e:
                            self.log(f"挂机奖励模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "商城":
                        try:
                            import shangcheng
                            shangcheng.main()
                            result = True
                        except ImportError as e:
                            self.log(f"商城模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "日常任务":
                        try:
                            import meirirenwulingqu
                            meirirenwulingqu.main()
                            result = True
                        except ImportError as e:
                            self.log(f"日常任务模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "爬塔":
                        try:
                            import pata
                            pata.main()
                            result = True
                        except ImportError as e:
                            self.log(f"爬塔模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "幻灵推图":
                        try:
                            import flow_push
                            ps = self.config.get("push_settings", {})
                            flow_push.main(
                                skip_manual=ps.get("skip_manual", True),
                                retry_count=ps.get("retry_count", 3)
                            )
                            result = True
                        except ImportError as e:
                            self.log(f"幻灵推图模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "推图":
                        try:
                            import push
                            ps = self.config.get("push_settings", {})
                            push.main(
                                skip_manual=ps.get("skip_manual", True),
                                retry_count=ps.get("retry_count", 3)
                            )
                            result = True
                        except ImportError as e:
                            self.log(f"推图模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "循环推图":
                        try:
                            import flow_push
                            import push
                            ps = self.config.get("push_settings", {})
                            skip_manual = ps.get("skip_manual", True)
                            retry_count = ps.get("retry_count", 3)
                            loop_count = 0
                            while not self.stop_event.is_set():
                                loop_count += 1
                                self.log(f"循环推图 第 {loop_count} 轮 - 幻灵推图开始")
                                try:
                                    flow_push.main(skip_manual=skip_manual, retry_count=retry_count)
                                except Exception as e:
                                    self.log(f"幻灵推图出错: {str(e)}")
                                
                                if self.stop_event.is_set():
                                    break
                                
                                self.log(f"循环推图 第 {loop_count} 轮 - 推图开始")
                                try:
                                    push.main(skip_manual=skip_manual, retry_count=retry_count)
                                except Exception as e:
                                    self.log(f"推图出错: {str(e)}")
                                
                                if self.stop_event.is_set():
                                    break
                                
                                self.log(f"循环推图 第 {loop_count} 轮完成，继续下一轮...")
                                time.sleep(2)
                            result = True
                        except ImportError as e:
                            self.log(f"循环推图模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    elif script.name == "异界迷宫":
                        try:
                            import flow_migong
                            challenges = script.params.get("challenges", 1)
                            shouling_action = "jieshutansuo" if script.params.get("floors") == "15" else "jixutansuo"
                            formation_name = script.params.get("formation_name", "")
                            shenceng_formation_name = script.params.get("shenceng_formation_name", "")
                            flow_migong.flow_migong(
                                challenges=challenges,
                                shouling_action=shouling_action,
                                formation_name=formation_name,
                                shenceng_formation_name=shenceng_formation_name,
                            )
                            result = True
                        except ImportError as e:
                            self.log(f"异界迷宫模块导入失败: {str(e)}")
                            script.status = "错误"
                            result = False
                    else:
                        self.log(f"{script.name} 脚本暂未实现")
                        result = False
                    
                if result:
                    script.status = "完成"
                    self.log(f"{script.name} 执行完成")
                    
                    # 更新最后执行时间
                    script.last_run_time = datetime.now().isoformat()
                    
                    # 对于每日重置的脚本，执行完成后自动关闭
                    if script.daily_reset:
                        script.enabled = False
                        self.log(f"{script.name} 已自动关闭（每日重置脚本）")
                else:
                    script.status = "失败"
                    self.log(f"{script.name} 执行失败")
                    
            except Exception as e:
                script.status = "错误"
                self.log(f"{script.name} 执行出错: {str(e)}")
                
            self.root.after(0, self.update_script_panel)
            
            if self.stop_event.is_set():
                break
                
            time.sleep(2)
        
        # 运行结束后保存（使 auto-disable / last_run_time 等状态持久化）
        self.save_config()
        self.root.after(0, self.stop_all)
        
    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        if self.log_text is not None:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, line)
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        else:
            if not hasattr(self, '_log_buffer'):
                self._log_buffer = []
            self._log_buffer.append(line)
    
    # ===== 配置持久化（load_config / save_config） =====
    def save_config(self):
        """保存配置"""
        # 收集脚本状态
        scripts_config = {}
        for script in self.scripts:
            scripts_config[script.name] = {
                "enabled": script.enabled,
                "params": script.params,
                "daily_reset": script.daily_reset,
                "last_run_time": script.last_run_time
            }
        self.config["scripts"] = scripts_config
        self.config["auto_start_on_launch"] = self.auto_start_on_launch
        self.config["launch_game_on_open"] = self.launch_game_on_open
        self.config["game_launch_delay"] = self.game_launch_delay
        self.config["schedule_time"] = self.schedule_time
        
        # 保存到文件
        if save_config(self.config):
            self.log("配置已保存")
        else:
            self.log("保存配置失败")

    def _auto_check_update(self):
        """启动时自动检查更新（后台线程）"""
        def _check():
            result = updater.check_update()
            if result[0] is None:
                return  # 启动时静默失败
            has_update, latest_tag, download_url, _ = result
            if has_update:
                self.root.after(0, lambda: self._show_update_dialog(latest_tag, download_url))
        threading.Thread(target=_check, daemon=True).start()

    def _check_update_clicked(self):
        """手动检查更新"""
        self.update_btn.configure(text="检查中...", state=tk.DISABLED)

        def _check():
            result = updater.check_update()
            if result[0] is None:
                _, err_msg = result
                self.root.after(0, lambda: self._update_result(f"检查失败: {err_msg}"))
            else:
                has_update, latest_tag, download_url, _ = result
                if has_update:
                    self.root.after(0, lambda: self._show_update_dialog(latest_tag, download_url))
                else:
                    self.root.after(0, lambda: self._update_result(f"已是最新版本 ({latest_tag})"))
            self.root.after(0, lambda: self.update_btn.configure(text="检查更新", state=tk.NORMAL))
        threading.Thread(target=_check, daemon=True).start()

    def _update_result(self, msg):
        self.version_label.configure(text=f"{__version__} - {msg}")
        self.log(msg)

    def _show_update_dialog(self, latest_tag, download_url):
        self.version_label.configure(text=f"{__version__} → {latest_tag} 可用", foreground="red")
        self.log(f"发现新版本: {latest_tag}")
        if not messagebox.askyesno("发现新版本",
                                   f"当前版本: {__version__}\n最新版本: {latest_tag}\n\n是否下载更新？"):
            return

        self.update_btn.configure(text="下载中...", state=tk.DISABLED)

        def _download():
            new_path = updater.download_update(download_url)
            if new_path is None:
                self.root.after(0, lambda: self._update_result("下载失败，请检查网络"))
                self.root.after(0, lambda: self.update_btn.configure(text="检查更新", state=tk.NORMAL))
                return
            self.root.after(0, lambda: self._install_and_restart(new_path))

        threading.Thread(target=_download, daemon=True).start()

    def _install_and_restart(self, new_path):
        self.update_btn.configure(text="检查更新", state=tk.NORMAL)
        if messagebox.askyesno("下载完成", "更新已下载，是否立即重启应用？"):
            updater.install_and_restart(new_path)

def main():
    root = tk.Tk()
    app = GameBotGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()