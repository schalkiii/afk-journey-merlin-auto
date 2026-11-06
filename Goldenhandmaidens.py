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

import contextlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

import common
import log_format
from version import __version__




# 启动 / 配置 / 窗口聚焦等独立工具抽到 bot_runtime，避免主文件过度膨胀
from bot_runtime import (
    ScriptConfig,
    _StdoutTee,
    _early_stdout_buffer,
    _early_stdout_sink,
    _ensure_config_files,
    append_log_file,
    focus_game_window,
    is_game_running,
    launch_game_by_shortcut,
    load_config,
    LOG_FILE,
    save_config,
    set_file_write_error_callback,
    _notify_file_write_error,
)

# updater 只在检查更新 / 下载 / 安装重启路径使用，延迟到用到时再导入以缩短启动

# 路径解析统一复用 common 的实现，避免与底层模块重复定义（见 common.get_resource_path / get_work_path）
from common import get_resource_path, get_work_path
from hero_metadata import (
    HERO_CN_NAMES,
    HERO_JOB,
    HERO_RACE,
    JOB_NAMES,
    PUSH_COMMON_HEROES,
    RACE_NAMES,
)
from warehouse import ALL_HERO_NAMES, WAREHOUSE_TXT_PATH

# 左侧功能列表的状态色（bg, fg, 短标签）：一眼扫出「正在跑哪个 / 哪个挂了」。
# 用经典 tk.Label 上色而不是给 ttk.Button 设 background——Windows 的 vista 主题会
# 忽略 ttk 控件的 background，只有 tk 控件能真正变色。
STATUS_COLORS = {
    "运行中": ("#1565C0", "white", "运行"),
    "等待中": ("#F9A825", "black", "排队"),
    "完成": ("#2E7D32", "white", "完成"),
    "失败": ("#C62828", "white", "失败"),
    "错误": ("#C62828", "white", "错误"),
    "已停止": ("#616161", "white", "停止"),
}
# 就绪（还没跑过）不抢视线：底色接近面板、文字留空
STATUS_NEUTRAL = ("#ECEFF1", "#90A4AE", "")

# 全局热键延后注册：keyboard 的导入 + add_hotkey 会让 `import Goldenhandmaidens`
# 之后的构造阶段多花约 0.15s，而这部分是阻塞启动的来源。把注册挪到首帧之后的
# after 回调里，双击图标到能操作会更快；代价是启动后约 0.2s 内 F8/F9 不可用，
# 属于可接受的取舍。
HOTKEY_REGISTER_DELAY_MS = 200

class GameBotGUI:
    def __init__(self, root):
        _ensure_config_files()
        self.root = root
        set_file_write_error_callback(self._schedule_file_write_error)
        self.root.title("梅林初号机")
        self.root.geometry("1200x880")
        self.root.minsize(1024, 640)
        
        # 全局默认字体
        style = ttk.Style()
        style.configure(".", font=("Microsoft YaHei", 9))

        self.is_running = False
        self.current_script_index = 0
        self.stop_event = threading.Event()
        # 热键注册被延后到首帧之后，注册前 _unregister_hotkeys 也可能被调用
        # （如窗口提前关闭 / 测试清理），先置空避免 AttributeError
        self._hotkey_lib = None
        self._hk_start = None
        self._hk_stop = None

        # 日志：先建缓冲，setup_ui 中创建可见日志框后再冲刷
        self.log_text = None
        self._log_buffer = []
        # 日志队列：工作线程只入队，主线程通过 after() 节流刷新，避免高频直冲 Tk 卡顿
        self._log_queue = queue.Queue()

        # 把各子脚本的调试日志（common.log）汇聚到应用内「运行日志」面板，同时落盘。
        # sink 必须是线程安全的（`log()` 只做入队 + 带锁追加文件，不碰 Tk 组件）；
        # UI 刷新由 _drain_log_queue 完成。之前只挂 _enqueue_log，盘上的 game_bot.log
        # 里完全没有子脚本行（实测用户跑完一轮后搜「家园愿望单」只剩开始/结束两条），
        # 而这些行恰恰是排查「识别没命中 / 没领到」最需要的。
        common.set_log_sink(self.log)
        # 注入停止检查器：F9 置位 stop_event 后，子脚本在下一次截图/点击
        # 原语调用处会抛出 StopRequested，实现「立即停止」而非等脚本跑完
        common.set_stop_checker(self.stop_event.is_set)

        # 加载配置
        self.config = load_config()
        self.auto_start_on_launch = self.config.get("auto_start_on_launch", False)
        self.auto_start_var = tk.BooleanVar(value=self.auto_start_on_launch)
        self.launch_game_on_open = self.config.get("launch_game_on_open", False)
        self.launch_game_var = tk.BooleanVar(value=self.launch_game_on_open)
        self.game_launch_delay = self.config.get("game_launch_delay", 20)
        self.game_wait_var = tk.IntVar(value=self.game_launch_delay)
        self.is_first_run = not self.config.get("first_run_completed", False)

        # 「自动配置通关阵容」选项：挑战前尝试自动采用 tongguanzhenrong / yijiancaiyong
        self.auto_configure_lineup = self.config.get("auto_configure_lineup", False)
        self.auto_configure_lineup_var = tk.BooleanVar(value=self.auto_configure_lineup)

        # 远程桌面兼容：后台截图（游戏被遮挡也能识别）+ 点击前自动激活游戏窗口。
        # 单屏远程桌面里机器人窗口常盖住游戏，普通截图/坐标点击都会落到机器人自己身上。
        self.remote_desktop_compat = self.config.get("remote_desktop_compat", True)
        self.remote_desktop_compat_var = tk.BooleanVar(value=self.remote_desktop_compat)
        common.set_background_capture(self.remote_desktop_compat)
        common.set_auto_activate(self.remote_desktop_compat)

        # 点击后归还鼠标位置：click_from_file 会把光标留在目标点，开着就每次点击后立即归位。
        # 窗口消息注入实测被本游戏忽略，无法做到完全后台点击，这是能做到的最小打扰。
        self.restore_cursor_after_click = self.config.get("restore_cursor_after_click", True)
        self.restore_cursor_var = tk.BooleanVar(value=self.restore_cursor_after_click)
        common.set_restore_cursor(self.restore_cursor_after_click)

        # 定时开始（每天循环）：存储为 "HH:MM" 或 None
        self.schedule_time = self.config.get("schedule_time", None)
        self.schedule_hour_var = tk.IntVar(value=8)
        self.schedule_min_var = tk.IntVar(value=0)
        self.schedule_active = False
        self.scheduled_time = None
        self.schedule_cancel_event = threading.Event()
        
        # 启用状态只由用户在左侧列表勾选，运行结束后不再自动改（原 daily_reset
        # 「完成即停用」会让第二天的任务被静默跳过，且改动会被持久化覆盖用户设置）。
        self.scripts = [
            ScriptConfig("登录", enabled=True),
            ScriptConfig("仓库管理", enabled=True),
            ScriptConfig("邮件", enabled=False),
            ScriptConfig("好友奖励", enabled=False),
            ScriptConfig("普竞", enabled=False),
            # 巅峰竞技场：每场消耗一次挑战次数，默认最多打 3 场
            ScriptConfig("巅峰竞技场", enabled=False, params={"challenge_count": 3}),
            ScriptConfig("迷梦之域", enabled=False, params={"challenge_count": 5}),
            ScriptConfig("女神塔", enabled=False),
            ScriptConfig("挂机奖励", enabled=False, params={"paid_times": 0}),
            ScriptConfig("商城", enabled=False),
            ScriptConfig("日常任务", enabled=False),
            # 红点领取覆盖任务面板各页签、赛季手册里程碑、月桂之旅与当前进度，
            # 与「日常任务」互补：日常任务只点每日/公会的一键领取。
            # 9 个子项默认全开，用户可在右侧面板逐项关闭（键名即 hongbaolingqu 读取的参数）。
            ScriptConfig("红点领取", enabled=False, params={
                "claim_daily": True,
                "claim_guild": True,
                "claim_growth": True,
                "claim_season": True,
                "claim_homestead": True,
                "claim_season_book": True,
                "claim_laurel": True,
                "claim_idle": True,
                "claim_guild_war": True,
            }),
            # 英雄厅堂：点「快速升级」提升赛季共鸣等级（每级吃共鸣资源，故给次数上限）
            ScriptConfig("英雄厅堂", enabled=False, params={"quick_upgrade_times": 10}),
            # 翻翻乐：一次点击会连抽到本轮 100 满，故给轮数上限（每轮最多烧 100 把钥匙）
            ScriptConfig("翻翻乐", enabled=False, params={"max_rounds": 10}),
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
            # 结社战线 / 狩猎悬赏 均为「玩法目录 → 公会玩法」页签下的公会日常，
            # 共用 flow_gonghui 的入口流程，结束后各自兜底回主界面。
            ScriptConfig("结社战线", enabled=False),
            ScriptConfig("狩猎悬赏", enabled=False),
            # 家园愿望单在「家园」内执行，结束后游戏停留在家园视图，而项目其余流程
            # 以主界面「玩法目录」为起点判定，故必须排在执行顺序末尾，避免阻断后续任务。
            ScriptConfig("家园愿望单", enabled=False),
        ]
        
        # 从配置中加载脚本状态
        for script in self.scripts:
            script_config = self.config.get("scripts", {}).get(script.name, {})
            script.enabled = script_config.get("enabled", script.enabled)
            script.params = script_config.get("params", script.params)
            script.last_run_time = script_config.get("last_run_time", None)

        # 恢复用户拖出来的执行顺序；配置里没有的功能（新版本新增）按默认顺序补到末尾
        saved_order = self.config.get("script_order") or []
        known = [s for s in self.scripts if s.name in saved_order]
        rest = [s for s in self.scripts if s.name not in saved_order]
        known.sort(key=lambda s: saved_order.index(s.name))
        self.scripts = known + rest
        
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

        # 注册全局热键 F8=开始运行 F9=停止运行。延后到首帧之后：keyboard 的
        # 导入与 add_hotkey 是阻塞启动的主要来源；必须留在主线程（注册依赖
        # 本线程的消息循环），所以用 after 而不是后台线程。
        self.root.after(HOTKEY_REGISTER_DELAY_MS, self._register_hotkeys)

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

        self.current_task_var = tk.StringVar(value="当前任务: 无")
        self.current_task_label = ttk.Label(
            top_frame, textvariable=self.current_task_var, foreground="blue"
        )
        self.current_task_label.pack(side=tk.RIGHT, padx=10)

        self.clear_log_btn = ttk.Button(
            control_frame,
            text="清空日志",
            command=self.clear_log_file
        )
        self.clear_log_btn.pack(side=tk.LEFT, padx=5)

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

        self.auto_configure_lineup_check = ttk.Checkbutton(
            opt_frame,
            text="自动配置通关阵容",
            variable=self.auto_configure_lineup_var,
            command=self.on_auto_configure_changed
        )
        self.auto_configure_lineup_check.pack(side=tk.LEFT, padx=5)

        self.remote_desktop_check = ttk.Checkbutton(
            opt_frame,
            text="远程桌面兼容（后台截图+自动激活）",
            variable=self.remote_desktop_compat_var,
            command=self.on_remote_desktop_changed
        )
        self.remote_desktop_check.pack(side=tk.LEFT, padx=5)

        self.restore_cursor_check = ttk.Checkbutton(
            opt_frame,
            text="点击后归还鼠标位置",
            variable=self.restore_cursor_var,
            command=self.on_restore_cursor_changed
        )
        self.restore_cursor_check.pack(side=tk.LEFT, padx=5)

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
        # 宽度要容下一行的三段：勾选框 + 状态色块 + 名称按钮（原来只有按钮，150 够）
        canvas = tk.Canvas(dashboard_frame, width=205, height=300)
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
        
        # 每行 = 启用勾选框 + 状态色块 + 名称按钮。启用状态直接在这一列勾选，
        # 不再放进右侧子页（原来「子页里一个开启勾选 + 列表 ✓ 前缀」是两份状态，
        # 用户看不出到底哪个算数）。拖拽仍然抓名称按钮，行 Frame 是 pack 单位。
        self.script_rows = []
        self.script_buttons = []
        self.script_checks = []
        self.script_status_labels = []
        self.script_enabled_vars = []
        for i, script in enumerate(self.scripts):
            row = tk.Frame(scrollable_frame)
            enabled_var = tk.BooleanVar(value=script.enabled)
            check = tk.Checkbutton(
                row, variable=enabled_var, width=2, takefocus=0,
                command=lambda idx=i, var=enabled_var: self.on_row_enabled_changed(idx, var)
            )
            check.pack(side=tk.LEFT)
            status_label = tk.Label(row, width=4, font=("Microsoft YaHei", 9))
            status_label.pack(side=tk.LEFT, padx=(0, 4))
            btn = ttk.Button(
                row,
                text=script.name,
                width=13,
                command=lambda idx=i: self.select_script(idx)
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
            row.pack(pady=4, fill=tk.X)
            # 按住上下拖动即可调整执行顺序；command 在松开时也会触发，故用 _drag_moved 抑制误选
            btn.bind("<ButtonPress-1>", lambda event, b=btn: self._drag_begin(event, b))
            btn.bind("<B1-Motion>", lambda event, b=btn: self._drag_motion(event, b))
            btn.bind("<ButtonRelease-1>", lambda event, b=btn: self._drag_end(event, b))
            self.script_rows.append(row)
            self.script_buttons.append(btn)
            self.script_checks.append(check)
            self.script_status_labels.append(status_label)
            self.script_enabled_vars.append(enabled_var)
            
        self.update_dashboard_buttons()

    # ===== 功能列表拖拽排序 =====
    # 列表顺序即执行顺序：run_scripts_thread 直接按 self.scripts 迭代，不再维护独立的
    # script_order 常量（原实现里按钮顺序与执行顺序是两份数据，拖动改了也不会生效）。
    def _drag_begin(self, event, button):
        self._drag_button = button
        self._drag_moved = False
        self._drag_start_y = event.y_root

    def _drop_index_at(self, root_y):
        """落点下标 = 第一个「垂直中点低于鼠标」的行下标，越过它即排到末尾。"""
        for index, row in enumerate(self.script_rows):
            if root_y < row.winfo_rooty() + row.winfo_height() // 2:
                return index
        return len(self.script_rows) - 1

    def _drag_motion(self, event, button):
        if not self._drag_moved and abs(event.y_root - self._drag_start_y) < 8:
            return   # 位移不足 8px 视为点击，不进入拖拽，避免误触改顺序
        self._drag_moved = True
        from_index = self.script_buttons.index(button)
        to_index = self._drop_index_at(event.y_root)
        if from_index != to_index:
            self._move_script(from_index, to_index)

    def _move_script(self, from_index, to_index):
        """把第 from 个功能移到 to 位置，数据顺序与各行 pack 顺序同步重排。"""
        selected_name = self.scripts[self.current_script_index].name
        # 数据与它的四份控件必须一起换位：漏一份，勾选框和状态色就会跟着错误的任务
        for collection in (
            self.scripts, self.script_rows, self.script_buttons, self.script_checks,
            self.script_status_labels, self.script_enabled_vars,
        ):
            item = collection.pop(from_index)
            collection.insert(to_index, item)

        for row in self.script_rows:
            row.pack_forget()
        for row in self.script_rows:
            row.pack(pady=4, fill=tk.X)

        # 按钮下标随重排变化，按名字找回当前选中项，避免面板显示到别的功能上
        self.current_script_index = next(
            i for i, s in enumerate(self.scripts) if s.name == selected_name
        )
        self.update_dashboard_buttons()

    def _drag_end(self, event, button):
        # _drag_moved 不在这里清掉：ttk Button 的 command 与本回调都在松开时触发，
        # 顺序不保证，留到下一次按下时再复位，select_script 才能可靠地跳过误选。
        if getattr(self, "_drag_moved", False):
            self.save_config()
            self.log("执行顺序已调整为：" + " → ".join(s.name for s in self.scripts))
            self.root.after(0, self.update_script_panel)
        
    def create_script_panel(self, parent):
        self.script_panel = ttk.LabelFrame(parent, text="配置", padding="10")
        self.script_panel.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.script_panel.columnconfigure(1, weight=1)
        
        self.script_name_label = ttk.Label(self.script_panel, text="", font=("Microsoft YaHei", 12, "bold"))
        self.script_name_label.grid(row=0, column=0, columnspan=2, pady=(0, 10))
        
        # 「开启」勾选框已移到左侧列表每行行首，子页不再重复放一份启用状态
        # 一键全选 / 全不选：每天启动后批量勾选 / 取消勾选所有功能脚本
        select_btns = ttk.Frame(self.script_panel)
        select_btns.grid(row=1, column=0, columnspan=2, sticky=tk.E, pady=5)
        self.select_all_btn = ttk.Button(
            select_btns, text="一键全选", command=self.enable_all_scripts
        )
        self.select_all_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.deselect_all_btn = ttk.Button(
            select_btns, text="一键全不选", command=self.disable_all_scripts
        )
        self.deselect_all_btn.pack(side=tk.LEFT)
        
        self.param_frame = ttk.Frame(self.script_panel)
        self.param_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # 单独运行：只跑当前选中的这一个功能，便于逐项验证 / 补跑漏掉的一天
        run_frame = ttk.Frame(self.script_panel)
        run_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5, 0))
        self.run_single_btn = ttk.Button(
            run_frame, text="只运行当前功能", command=self.run_single_script
        )
        self.run_single_btn.pack(side=tk.LEFT)
        ttk.Label(run_frame, text="（忽略其它勾选）", foreground="gray").pack(side=tk.LEFT, padx=5)

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
        if self.log_text is None:
            return
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
        
        def refresh_log():
            try:
                with open(LOG_FILE, encoding="utf-8") as f:
                    content = f.read()
            except FileNotFoundError:
                content = ""
            except Exception as e:
                content = f"读取日志失败: {e}\n"
            log_text.configure(state=tk.NORMAL)
            log_text.delete("1.0", tk.END)
            log_text.insert(tk.END, content)
            log_text.see(tk.END)
            log_text.configure(state=tk.DISABLED)

        log_text.configure(state=tk.DISABLED)
        button_frame = ttk.Frame(log_frame)
        button_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))
        ttk.Button(button_frame, text="刷新", command=refresh_log).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="清空文件", command=self.clear_log_file).pack(side=tk.LEFT)
        refresh_log()

    def clear_log_file(self):
        if not messagebox.askyesno("清空日志", "确定要清空本地日志文件吗？"):
            return
        try:
            with open(LOG_FILE, "w", encoding="utf-8"):
                pass
            self.log_text.delete("1.0", tk.END)
            timestamp = time.strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] 本地日志文件已清空（此提示不会写入文件）\n")
            self.log_text.see(tk.END)
        except Exception as e:
            messagebox.showerror("清空失败", str(e))

    def show_help_window(self):
        help_window = tk.Toplevel(self.root)
        help_window.title("帮助")
        help_window.geometry("700x650")

        readme_path = get_resource_path("README.md")
        if os.path.exists(readme_path):
            with open(readme_path, encoding="utf-8") as f:
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
        """刷新左侧列表：选中高亮、启用勾选状态、以及每行的状态色块。"""
        for index, script in enumerate(self.scripts):
            btn = self.script_buttons[index]
            btn.state(['pressed'] if index == self.current_script_index else ['!pressed'])
            # 名称不再加 ✓ 前缀：启用状态已由行首勾选框表达，两处各写一份迟早互相打脸
            btn.configure(text=script.name)
            self.script_enabled_vars[index].set(script.enabled)
            background, foreground, short_text = STATUS_COLORS.get(
                script.status, STATUS_NEUTRAL)
            self.script_status_labels[index].configure(
                text=short_text, bg=background, fg=foreground)

    def on_row_enabled_changed(self, index, var):
        """行首勾选框改动启用状态：只按用户意图写入并立即持久化。"""
        self.scripts[index].enabled = var.get()
        self.save_config()
    def update_script_panel(self):
        script = self.scripts[self.current_script_index]
        self.script_name_label.configure(text=script.name)
        # 运行循环每改一次 status 都会经本方法刷新（root.after 派发），
        # 顺带刷左侧行首的勾选框与状态色，避免同一份状态要两个入口各自维护。
        self.update_dashboard_buttons()

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
        elif script.name == "巅峰竞技场":
            self.create_dianfeng_params(script, 0)
        elif script.name == "挂机奖励":
            self.create_shouquguajijiangli_params(script, 0)
        elif script.name == "英雄厅堂":
            self.create_yingxiong_params(script, 0)
        elif script.name == "翻翻乐":
            self.create_fanfanle_params(script, 0)
        elif script.name == "异界迷宫":
            self.create_yijiemigong_params(script, 0)
        elif script.name in ("幻灵推图", "推图", "循环推图"):
            self.create_push_params(0)
        elif script.name == "仓库管理":
            self.create_warehouse_params(0)
        elif script.name == "红点领取":
            self.create_hongbao_params(script, 0)
            
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

        # 进入迷梦后领取排行榜礼包（实测角标挂在右侧「排行榜」图标上）
        self.mimeng_claim_var = tk.BooleanVar(value=script.params.get("claim_reward", True))
        ttk.Checkbutton(
            self.param_frame,
            text="领取排行榜礼包",
            variable=self.mimeng_claim_var,
            command=lambda: (script.params.__setitem__("claim_reward", self.mimeng_claim_var.get()),
                             self.save_config())
        ).grid(row=row + 1, column=0, columnspan=2, sticky=tk.W, pady=2)

    def create_dianfeng_params(self, script, row=0):
        """巅峰竞技场参数：单次运行最多挑战几场。"""
        ttk.Label(self.param_frame, text="挑战场数 (1-10):").grid(
            row=row, column=0, sticky=tk.W, pady=2)
        self.dianfeng_count_var = tk.IntVar(value=script.params.get("challenge_count", 3))
        spinbox = ttk.Spinbox(
            self.param_frame, from_=1, to=10,
            textvariable=self.dianfeng_count_var, width=10
        )
        spinbox.grid(row=row, column=1, sticky=tk.W, pady=2)

        def on_param_change():
            script.params["challenge_count"] = self.dianfeng_count_var.get()
            self.save_config()

        spinbox.bind("<FocusOut>", lambda e: on_param_change())
        spinbox.bind("<Return>", lambda e: on_param_change())

    def create_yingxiong_params(self, script, row=0):
        """英雄厅堂参数：每次运行最多点几次「快速升级」。"""
        ttk.Label(self.param_frame, text="快速升级次数 (1-99):").grid(row=row, column=0, sticky=tk.W, pady=2)

        self.quick_upgrade_times_var = tk.IntVar(value=script.params.get("quick_upgrade_times", 10))
        spinbox = ttk.Spinbox(
            self.param_frame,
            from_=1,
            to=99,
            textvariable=self.quick_upgrade_times_var,
            width=10
        )
        spinbox.grid(row=row, column=1, sticky=tk.W, pady=2)

        def on_param_change():
            # 每升一级都要吃共鸣资源，次数上限防止把资源一次点光
            script.params["quick_upgrade_times"] = self._clamp_int_var(self.quick_upgrade_times_var, 1, 99)
            self.save_config()

        spinbox.bind("<FocusOut>", lambda e: on_param_change())
        spinbox.bind("<Return>", lambda e: on_param_change())

    def create_fanfanle_params(self, script, row=0):
        """翻翻乐参数：每次运行最多烧几轮（一轮最多消耗 100 把钥匙）。"""
        ttk.Label(self.param_frame, text="最多轮数 (1-50):").grid(row=row, column=0, sticky=tk.W, pady=2)

        self.fanfanle_max_rounds_var = tk.IntVar(value=script.params.get("max_rounds", 10))
        spinbox = ttk.Spinbox(
            self.param_frame,
            from_=1,
            to=50,
            textvariable=self.fanfanle_max_rounds_var,
            width=10
        )
        spinbox.grid(row=row, column=1, sticky=tk.W, pady=2)

        def on_param_change():
            # 一次点击就会连抽到本轮 100 满，轮数上限防止把钥匙一次性烧光
            script.params["max_rounds"] = self._clamp_int_var(self.fanfanle_max_rounds_var, 1, 50)
            self.save_config()

        spinbox.bind("<FocusOut>", lambda e: on_param_change())
        spinbox.bind("<Return>", lambda e: on_param_change())

    def create_hongbao_params(self, script, row=0):
        """红点领取的子项开关：勾选后运行时才去对应页签 / 里程碑领取，默认全开。"""
        options = (
            ("claim_daily", "每日任务"),
            ("claim_guild", "公会任务"),
            ("claim_growth", "成长挑战"),
            ("claim_season", "赛季任务"),
            ("claim_homestead", "家园目标"),
            ("claim_season_book", "赛季手册"),
            ("claim_laurel", "月桂之旅"),
            ("claim_idle", "赛季挂机关卡"),
            ("claim_guild_war", "公会征伐"),
        )
        self.hongbao_claim_vars = {}
        for index, (key, label) in enumerate(options):
            var = tk.BooleanVar(value=bool(script.params.get(key, True)))
            self.hongbao_claim_vars[key] = var

            def on_toggle(k=key, v=var):
                script.params[k] = bool(v.get())
                self.save_config()

            ttk.Checkbutton(
                self.param_frame, text=label, variable=var, command=on_toggle
            ).grid(row=row + index // 2, column=index % 2, sticky=tk.W, pady=2)

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

        # 进入推图界面后领取「赛季阶段排名 → 首通」奖励（固定点位，带界面自证）
        claim_first_clear = push_settings.get("claim_first_clear", True)
        self.claim_first_clear_var = tk.BooleanVar(value=claim_first_clear)
        ttk.Checkbutton(
            self.param_frame,
            text="进入后领取赛季首通奖励",
            variable=self.claim_first_clear_var,
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

        # 连续失败上限：跨阵容累计，达到后结束本轮推图（避免阵容全灭后无限重试）
        ttk.Label(self.param_frame, text="连续失败上限 (1-99):").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.max_failures_var = tk.IntVar(
            value=push_settings.get("max_consecutive_failures", 10)
        )
        ttk.Spinbox(
            self.param_frame,
            from_=1,
            to=99,
            textvariable=self.max_failures_var,
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

    @staticmethod
    def _clamp_int_var(var, default, minimum, maximum):
        """读取 Spinbox 变量并收敛到合法范围；空值/非法输入回退默认值。"""
        try:
            value = int(var.get())
        except (tk.TclError, ValueError, TypeError):
            value = default
        value = max(minimum, min(maximum, value))
        var.set(value)
        return value

    def on_push_param_change(self):
        self.config["push_settings"] = {
            "skip_manual": self.skip_manual_var.get(),
            "claim_first_clear": self.claim_first_clear_var.get(),
            "retry_count": self._clamp_int_var(self.retry_count_var, 3, 1, 3),
            "max_consecutive_failures": self._clamp_int_var(self.max_failures_var, 10, 1, 99),
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
            with open(WAREHOUSE_TXT_PATH, encoding='utf-8') as f:
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
            _notify_file_write_error(WAREHOUSE_TXT_PATH)
            self.log(f"写入仓库文件失败: {str(e)}")

    def _schedule_file_write_error(self, path):
        if getattr(self, "_file_write_error_notified", False):
            return
        self._file_write_error_notified = True
        self._file_write_error_pending = True
        self.root.after(0, lambda: self._show_file_write_error(path))

    def _show_file_write_error(self, path):
        self._file_write_error_pending = False
        messagebox.showerror(
            "文件写入失败",
            f"无法写入文件：\n{path}\n\n"
            "当前文件夹可能没有写入权限，请将程序移动到其他可写文件夹后重试。",
        )
    
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
        # 加载 formations.json 获取阵容列表（exe 同目录的可编辑副本优先）
        formations = {}
        try:
            with open(common.get_config_path("formations.json"), encoding="utf-8") as f:
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
        # 拖拽松手时 ttk Button 也会触发 command，此时应视为「调整顺序」而非「选中该功能」
        if getattr(self, "_drag_moved", False):
            return
        self.current_script_index = index
        self.update_dashboard_buttons()
        self.update_script_panel()
        
    def enable_all_scripts(self):
        """一键勾选全部功能脚本：每天启动后批量启用，省去逐个勾选。"""
        for script in self.scripts:
            script.enabled = True
        self.update_dashboard_buttons()  # 刷新左侧各行行首的勾选框
        self.save_config()               # 持久化到配置
        self.log("已一键勾选全部功能")

    def disable_all_scripts(self):
        """一键取消勾选全部功能脚本：批量停用，省去逐个取消。"""
        for script in self.scripts:
            script.enabled = False
        self.update_dashboard_buttons()  # 刷新左侧各行行首的勾选框
        self.save_config()               # 持久化到配置
        self.log("已一键取消勾选全部功能")

    def on_auto_start_changed(self):
        self.auto_start_on_launch = self.auto_start_var.get()
        self.save_config()

    def on_launch_game_changed(self):
        self.launch_game_on_open = self.launch_game_var.get()
        self.save_config()

    def on_auto_configure_changed(self):
        self.auto_configure_lineup = self.auto_configure_lineup_var.get()
        self.config["auto_configure_lineup"] = self.auto_configure_lineup
        self.save_config()

    def on_remote_desktop_changed(self):
        """切换远程桌面兼容：同时控制后台截图与点击前自动激活。"""
        self.remote_desktop_compat = self.remote_desktop_compat_var.get()
        common.set_background_capture(self.remote_desktop_compat)
        common.set_auto_activate(self.remote_desktop_compat)
        self.save_config()
        state = "开启" if self.remote_desktop_compat else "关闭"
        self.log(f"远程桌面兼容模式已{state}")

    def on_restore_cursor_changed(self):
        """切换「点击后归还鼠标位置」。"""
        self.restore_cursor_after_click = self.restore_cursor_var.get()
        common.set_restore_cursor(self.restore_cursor_after_click)
        self.save_config()
        state = "开启" if self.restore_cursor_after_click else "关闭"
        self.log(f"点击后归还鼠标位置已{state}")

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

    def _set_current_task(self, name):
        """主线程更新「当前任务」标签与窗口标题，便于远程查看运行到哪一项。"""
        self.current_task_var.set(f"当前任务: {name}")
        if name == "无":
            self.root.title("梅林初号机")
        else:
            self.root.title(f"梅林初号机 - 运行中: {name}")

    def start_all(self):
        """按功能列表当前顺序运行全部已勾选的功能。"""
        self._reset_stale_run_state()
        if self.is_running:
            messagebox.showwarning("提示", "已有任务在运行中，请先停止 (F9)。")
            return
        enabled_scripts = [s for s in self.scripts if s.enabled]
        if not enabled_scripts:
            messagebox.showwarning("警告", "没有启用任何脚本！")
            return
        self._begin_run(enabled_scripts)
        self.log("开始运行脚本")

    def run_single_script(self):
        """只运行当前选中的这一个功能，忽略其它勾选：便于逐项验证或补跑漏掉的一天。"""
        self._reset_stale_run_state()
        if self.is_running:
            messagebox.showwarning("提示", "已有任务在运行中，请先停止 (F9)。")
            return
        script = self.scripts[self.current_script_index]
        self._begin_run([script], respect_enabled=False)
        self.log(f"单独运行: {script.name}")

    def _prepare_run_statuses(self, scripts_to_run, respect_enabled=True):
        """按本轮实际执行范围复位左侧状态：不跑的脚本回「就绪」，只给要跑的标「等待中」。

        旧实现把 self.scripts 全部置「等待中」，未勾选的邮件/仓库管理也跟着排队，
        用户无法一眼看出本轮到底跑哪些。respect_enabled=False 用于「只运行当前功能」：
        忽略勾选，只把传入的那一个标为等待。
        """
        for script in self.scripts:
            script.status = "就绪"
        if respect_enabled:
            targets = [s for s in scripts_to_run if s.enabled]
        else:
            targets = list(scripts_to_run)
        for script in targets:
            script.status = "等待中"

    def _clear_pending_statuses(self):
        """运行循环提前结束时，把还没轮到执行的「等待中」收回「就绪」。"""
        for script in self.scripts:
            if script.status == "等待中":
                script.status = "就绪"

    def _begin_run(self, scripts_to_run, respect_enabled=True):
        """启动运行线程的公共入口：置运行态、复位状态标记、拉起工作线程。"""
        self.is_running = True
        self.stop_event.clear()
        self.update_master_button()

        self._prepare_run_statuses(scripts_to_run, respect_enabled)
        self.update_script_panel()

        thread = threading.Thread(
            target=self.run_scripts_thread,
            args=(scripts_to_run, respect_enabled),
        )
        thread.daemon = True
        self._run_thread = thread
        thread.start()

    def _reset_stale_run_state(self):
        """上次运行线程已结束但 is_running 未复位时，自动清理，避免误报「请先按 F9」。

        历史 bug：任务切换兜底（关闭礼包/回主界面）在 try 之外抛出异常时，
        工作线程直接退出，末尾的 stop_all 没执行，is_running 永远停在 True。
        """
        thread = getattr(self, "_run_thread", None)
        if self.is_running and (thread is None or not thread.is_alive()):
            self.log("检测到上次运行线程已结束但运行状态未复位，已自动清理")
            self.is_running = False
            self.update_master_button()
            self._clear_pending_statuses()
            self._set_current_task("无")
        
    def stop_all(self):
        self.stop_event.set()
        self.is_running = False
        self.update_master_button()
        self._set_current_task("无")
        
        for script in self.scripts:
            if script.status == "运行中":
                script.status = "已停止"
            elif script.status == "等待中":
                # 没轮到的任务别继续留在「排队」，停止后应回到未执行的中性状态
                script.status = "就绪"
        self.update_script_panel()
        
        self.log("所有脚本已停止")
        
    def on_closing(self):
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
        """按需启动游戏，等游戏就绪后开始脚本流程。

        「立即开始」与「启动游戏」解耦：游戏已在运行时不再按快捷方式重复拉起
        （会多开客户端/弹启动器），直接 0 延迟开始脚本；launch_game=False 同理。
        """
        if self.is_running:
            self.log("脚本已在运行中，忽略本次启动请求")
            return
        enabled = [s for s in self.scripts if s.enabled]
        if not enabled:
            messagebox.showwarning("警告", "没有启用任何脚本！")
            return
        if launch_game and not is_game_running():
            self.launch_game_from_shortcut()
            delay = self.game_launch_delay
            self.log(f"{delay} 秒后将开始运行脚本流程")
        elif launch_game:
            delay = 0
            self.log("游戏已在运行，跳过启动，立即开始脚本")
        else:
            delay = 0
            self.log("不启动游戏，立即开始脚本")
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
            if self.scheduled_time is None:
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
        remaining = max(remaining, 0)
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
    def is_click_from_file_running(self):
        """检测 click_from_file.exe 是否已在运行，避免重复启动造成卡顿与弹框。"""
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq click_from_file.exe"],
                capture_output=True, text=True
            )
            return "click_from_file.exe" in result.stdout
        except Exception:
            return False

    # ===== 任务分发（字典映射替代巨型 if/elif，降低维护成本）=====
    # 每个 _run_* 方法对应一个任务，返回 True 表示执行成功、False 表示失败；
    # 内部 import 失败抛 ImportError 由 _run_script_dispatch 统一捕获并记日志。
    def _run_login(self, script):
        import start
        # 登录流程没有失败语义：找不到开始界面说明游戏已在登录态，属正常跳过，故恒为成功
        start.main()
        return True

    def _run_warehouse(self, script):
        if not os.path.exists(WAREHOUSE_TXT_PATH):
            self._write_warehouse_txt()
        self.log("仓库英雄数据已就绪")
        return True

    def _run_youjian(self, script):
        import youjian
        return youjian.main()

    def _run_haoyou(self, script):
        import haoyoujiangli
        return haoyoujiangli.main()

    def _run_pujing(self, script):
        import pujing
        return pujing.flow_pujing()

    def _run_mimeng(self, script):
        from mimengzhiyu import flow_mimengzhiyu
        challenge_count = script.params.get("challenge_count")
        return flow_mimengzhiyu(
            challenge_count=challenge_count,
            auto_configure_lineup=self.auto_configure_lineup,
            claim_reward=script.params.get("claim_reward", True),
        )

    def _run_dianfeng(self, script):
        import dianfengjingjichang
        return dianfengjingjichang.flow_dianfeng(
            challenge_count=script.params.get("challenge_count", 3)
        )

    def _run_nvshenta(self, script):
        import nvshenta
        return nvshenta.flow_nvshenta(auto_configure_lineup=self.auto_configure_lineup)

    def _run_guajijiangli(self, script):
        import shouquguajijiangli
        paid_times = script.params.get("paid_times", 0)
        return shouquguajijiangli.main(paid_times=paid_times)

    def _run_shangcheng(self, script):
        import shangcheng
        return shangcheng.main()

    def _run_meiri(self, script):
        import meirirenwulingqu
        return meirirenwulingqu.main()

    def _run_yingxiongtingtang(self, script):
        import yingxiongtingtang
        return yingxiongtingtang.main(script.params.get("quick_upgrade_times", 10))

    def _run_fanfanle(self, script):
        import fanfanle
        return fanfanle.main(script.params.get("max_rounds", 10))

    def _run_hongbaolingqu(self, script):
        import hongbaolingqu
        # 子项开关随 params 透传，运行时由 hongbaolingqu 按 claim_* 逐项决定是否领取
        return hongbaolingqu.main(params=script.params)

    def _run_yuanwangdan(self, script):
        import yuanwangdan
        return yuanwangdan.main()

    def _run_jieshezhanxian(self, script):
        import jieshezhanxian
        return jieshezhanxian.main()

    def _run_lieshouxunshang(self, script):
        import lieshouxunshang
        return lieshouxunshang.main()

    def _run_pata(self, script):
        import pata
        return pata.main()

    def _run_huanling(self, script):
        import flow_push
        ps = self.config.get("push_settings", {})
        flow_push.main(
            skip_manual=ps.get("skip_manual", True),
            retry_count=ps.get("retry_count", 3),
            max_consecutive_failures=ps.get("max_consecutive_failures", 10),
            claim_first_clear=ps.get("claim_first_clear", True),
        )
        return True

    def _run_tu_tu(self, script):
        import push
        ps = self.config.get("push_settings", {})
        # push.main 返回 True=正常结束 / False=流程异常结束，直接作为任务结果
        return bool(push.main(
            skip_manual=ps.get("skip_manual", True),
            retry_count=ps.get("retry_count", 3),
            max_consecutive_failures=ps.get("max_consecutive_failures", 10),
            claim_first_clear=ps.get("claim_first_clear", True),
        ))

    def _ensure_loop_ready(self):
        """循环推图模式切换前兜底：清弹窗并回主界面，避免停在战斗失败/结算页空转。"""
        common.dismiss_popup()
        if common.ensure_main_interface():
            return True
        self.log("循环推图：无法回到主界面，停止循环。")
        return False

    def _run_xunhuan(self, script):
        import flow_push
        import push
        ps = self.config.get("push_settings", {})
        skip_manual = ps.get("skip_manual", True)
        claim_first_clear = ps.get("claim_first_clear", True)
        retry_count = ps.get("retry_count", 3)
        max_failures = ps.get("max_consecutive_failures", 10)
        loop_count = 0
        fast_rounds = 0
        while not self.stop_event.is_set():
            # 幻灵推图失败可能停在「战斗失败」等模态页，不先恢复主界面会导致
            # 本轮普通推图和后续轮次都卡在 wanfamulu 等待上空转（实测踩过）。
            if not self._ensure_loop_ready():
                break
            loop_count += 1
            round_start = time.time()
            self.log(f"循环推图 第 {loop_count} 轮 - 幻灵推图开始")
            try:
                huanling_result = flow_push.main(
                    skip_manual=skip_manual,
                    retry_count=retry_count,
                    max_consecutive_failures=max_failures,
                    claim_first_clear=claim_first_clear,
                )
                if flow_push.LAST_STOP_REASON == "fail_limit":
                    self.log(f"幻灵推图连续失败达到 {max_failures} 次，停止循环推图。")
                    break
                if huanling_result is False:
                    # 单个模式结束/失败不是循环失败，按设计切换到普通推图继续下一轮
                    self.log("幻灵推图流程结束，切换到普通推图。")
            except Exception as e:
                self.log(f"幻灵推图出错: {e!s}")
                self.log("幻灵推图异常，继续切换到普通推图。")

            if self.stop_event.is_set():
                break

            # 幻灵推图与普通推图各自从主界面进入；模式切换前同样先恢复，
            # 单模式结束/失败后不能假定界面已经回到主界面。
            if not self._ensure_loop_ready():
                break

            self.log(f"循环推图 第 {loop_count} 轮 - 推图开始")
            try:
                push_result = push.main(
                    skip_manual=skip_manual,
                    retry_count=retry_count,
                    max_consecutive_failures=max_failures,
                    claim_first_clear=claim_first_clear,
                )
                if push.LAST_STOP_REASON == "fail_limit":
                    self.log(f"推图连续失败达到 {max_failures} 次，停止循环推图。")
                    break
                if push_result is False:
                    # 单个模式结束/失败不是循环失败，下一轮重新进入幻灵推图
                    self.log("普通推图流程结束，下一轮切换到幻灵推图。")
            except Exception as e:
                self.log(f"推图出错: {e!s}")
                self.log("普通推图异常，下一轮继续切换到幻灵推图。")

            if self.stop_event.is_set():
                break

            round_cost = time.time() - round_start
            # 一轮正常推图至少包含一次战斗，通常需要几十秒以上；
            # 30 秒内就结束的轮次视为异常（快速失败/空转）。
            if round_cost < 30:
                fast_rounds += 1
                self.log(f"本轮耗时 {round_cost:.1f} 秒，异常快速结束（连续 {fast_rounds} 轮）")
            else:
                fast_rounds = 0

            if fast_rounds >= 3:
                self.log("循环推图连续 3 轮在 30 秒内异常结束，判定流程异常，停止循环推图。")
                break

            self.log(f"循环推图 第 {loop_count} 轮完成，继续下一轮...")
            time.sleep(2)
        return True

    def _run_migong(self, script):
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
        return True

    def _run_script_dispatch(self, script_name, script):
        """按脚本名分发到对应执行函数；未实现或导入失败返回 False。"""
        runners = {
            "登录": self._run_login,
            "仓库管理": self._run_warehouse,
            "邮件": self._run_youjian,
            "好友奖励": self._run_haoyou,
            "普竞": self._run_pujing,
            "巅峰竞技场": self._run_dianfeng,
            "迷梦之域": self._run_mimeng,
            "女神塔": self._run_nvshenta,
            "挂机奖励": self._run_guajijiangli,
            "商城": self._run_shangcheng,
            "日常任务": self._run_meiri,
            "红点领取": self._run_hongbaolingqu,
            "翻翻乐": self._run_fanfanle,
            "英雄厅堂": self._run_yingxiongtingtang,
            "结社战线": self._run_jieshezhanxian,
            "狩猎悬赏": self._run_lieshouxunshang,
            "家园愿望单": self._run_yuanwangdan,
            "爬塔": self._run_pata,
            "幻灵推图": self._run_huanling,
            "推图": self._run_tu_tu,
            "循环推图": self._run_xunhuan,
            "异界迷宫": self._run_migong,
        }
        runner = runners.get(script_name)
        if runner is None:
            self.log(f"{script.name} 脚本暂未实现")
            return False
        try:
            return runner(script)
        except ImportError as e:
            self.log(f"{script.name} 模块导入失败: {e!s}")
            return False

    def run_scripts_thread(self, scripts_to_run, respect_enabled=True):
        # 单运行循环假设：log_format._task 是模块级全局，两个并行循环会互相覆盖任务上下文，
        # 日志归组随之错乱。断言放在任何 set_task 之前，确保同一时刻只有一个循环在跑。
        assert log_format.current_task() is None, (
            "已有运行循环在执行（log_format 任务上下文非空），禁止并行启动第二个运行循环"
        )
        # 先把子脚本的 print 调试日志转发到运行日志面板（经队列，主线程节流刷新）
        sys.stdout = _StdoutTee(self._enqueue_log)

        capture_mode = "后台截图(WGC)" if self.remote_desktop_compat else "前台屏幕截图"
        activate_mode = "开" if self.remote_desktop_compat else "关"
        self.log(f"截图模式: {capture_mode}；点击前自动激活游戏: {activate_mode}")
        region = common.game_client_region()
        if region and (region[2], region[3]) != (1600, 900):
            self.log(
                f"警告: 游戏客户区当前为 {region[2]}×{region[3]}，模板按 1600×900 采集，"
                "识别可能失败；请把游戏窗口恢复为 1600×900"
            )

        # click_from_file.exe 是常驻监听程序（与各脚本通过 shared 目录 IPC 通信）。
        # 若已在运行则直接复用，避免每次点「开始」都重启 + 弹出新终端框造成约 1 秒卡顿；
        # 仅当未运行时才启动，并用 CREATE_NO_WINDOW 隐藏控制台窗口（性能与体验优化）。
        if self.is_click_from_file_running():
            self.log("click_from_file.exe 已在运行，复用现有进程（跳过重启）")
        else:
            try:
                subprocess.run(["taskkill", "/F", "/IM", "click_from_file.exe"], capture_output=True)
                time.sleep(0.3)
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
                    # CREATE_NO_WINDOW：Windows 下不弹出控制台黑框，消除「启动终端框」的视觉卡顿
                    subprocess.Popen([ahk_exe_path, work_dir], creationflags=subprocess.CREATE_NO_WINDOW)
                    self.log("click_from_file.exe 启动成功")
            except Exception as e:
                self.log(f"运行click_from_file.exe失败: {e!s}")
                self.log("警告: click_from_file.exe 未启动，部分功能可能无法正常工作")
            time.sleep(2)
        
        # 按调用方给定的脚本列表依次执行。列表由 start_all / run_single_script 从
        # self.scripts 生成，因此顺序就是功能列表里拖出来的顺序——不再维护独立的
        # script_order 常量（那样按钮顺序和执行顺序是两份数据，拖动改了也不生效）。
        total = len(scripts_to_run)
        for index, script in enumerate(list(scripts_to_run), 1):
            if self.stop_event.is_set():
                break

            if respect_enabled and not script.enabled:
                continue

            script.status = "运行中"
            self.root.after(0, self.update_script_panel)
            self.root.after(0, self._set_current_task, f"{script.name} ({index}/{total})")
            # 任务上下文必须**同步**设好：子脚本的行是紧接着 print 出来的，
            # 靠 root.after 异步设置会漏掉紧随的几行，那些行就不会归组缩进。
            log_format.set_task(script.name)
            self.log(log_format.task_start_line(index, total, script.name))
            task_started = time.time()

            # 点击器退出后所有任务都只会空转，逐轮跑下去毫无意义：开局先确认它还活着
            if not common.clicker_alive():
                script.status = "失败"
                self.log("click_from_file.exe 未在消费坐标（可能已退出或被拦截），已中止后续任务")
                break

            # 任务切换兜底：
            # 1) 先关闭上一任务残留的礼包广告 / 结算 / 战斗失败弹窗；
            # 2) 再确保已回到主界面（wanfamulu 可见）。若上一任务卡在子界面未退出，
            #    逐层退出回到主界面，避免本次 wanfamulu 检测失败、连锁卡死后续所有任务。
            try:
                common.dismiss_popup()
                if script.name != "登录":
                    common.ensure_main_interface()

                # 检查是否需要停止
                if self.stop_event.is_set():
                    script.status = "已停止"
                    self.log(f"{script.name} 已停止")
                    result = False
                else:
                    # 字典分发：_run_script_dispatch 按脚本名调用对应 _run_* 方法，
                    # 导入失败统一捕获并返回 False（状态由下方 if/else 置为「失败」）
                    result = self._run_script_dispatch(script.name, script)

                duration = time.time() - task_started
                if result:
                    script.status = "完成"
                    self.log(log_format.task_end_line(True, index, total, script.name, duration))

                    # 更新最后执行时间。这里**不再**改动 script.enabled：
                    # 旧的「每日重置脚本跑完自动关闭」会把用户的勾选写回配置，
                    # 导致第二天该任务被静默跳过，且用户下次打开看到的是被程序改过的设置。
                    script.last_run_time = datetime.now().isoformat()
                else:
                    script.status = "失败"
                    self.log(log_format.task_end_line(False, index, total, script.name, duration))
                    # 失败/超时留存最近几帧画面，便于事后定位「当时卡在哪一屏」；
                    # F9 主动停止不算失败现场，不落盘。
                    if not self.stop_event.is_set():
                        common.capture_failure_context(script.name, "任务失败或超时")
                    
            except common.StopRequested:
                script.status = "已停止"
                self.log(f"{script.name} 已被停止 (F9)")
                self.root.after(0, self.update_script_panel)
                break
            except Exception as e:
                script.status = "错误"
                self.log(log_format.task_end_line(False, index, total, script.name,
                                                  time.time() - task_started) + f" 出错: {e!s}")
                # 异常同样留存现场，原因带上异常文本，方便与日志首行对应
                common.capture_failure_context(script.name, f"任务执行异常: {e!s}")
                # 完整堆栈写入日志文件便于定位；逐行加时间戳并归到当前任务下，
                # 面板仍只显示上面那条首行，避免刷屏
                for stack_line in log_format.format_multiline(traceback.format_exc()):
                    stamp = time.strftime('%H:%M:%S')
                    append_log_file(f'[{stamp}] {stack_line}\n')
            finally:
                # 任务一结束就摘掉上下文，任务之间的等待/收尾行不再被误缩进到上一任务里
                log_format.set_task(None)
                
            self.root.after(0, self.update_script_panel)
            
            if self.stop_event.is_set():
                break
                
            time.sleep(2)
        
        # 运行结束后保存（使 last_run_time 等状态持久化；勾选状态只反映用户自己的设置）
        # 保持 tee 接管（窗口模式下 sys.__stdout__ 为 None，直接重置会令后续 print 崩溃）
        sys.stdout = _StdoutTee(self._enqueue_log)
        self._clear_pending_statuses()
        self.root.after(0, self._set_current_task, "无")
        self.save_config()
        self.root.after(0, self.stop_all)
        
    def _enqueue_log(self, message):
        """日志汇聚回调（工作线程调用）：仅把消息放入队列，线程安全、零 Tk 操作。"""
        with contextlib.suppress(Exception):
            self._log_queue.put_nowait(str(message))

    def _drain_log_queue(self):
        """主线程定时（节流）冲刷日志队列：批量追加、限制行数、一次性滚到底部。

        相比「每来一条就 configure/insert/see 三次 Tk 操作」的旧实现，
        批量写入 + 行数封顶显著降低高频日志下的 UI 卡顿。约每 120ms 刷新一次。
        """
        try:
            if not self._log_queue.empty():
                lines = []
                while True:
                    try:
                        lines.append(self._log_queue.get_nowait())
                    except queue.Empty:
                        break
                if lines:
                    buf = "".join(f"[{time.strftime('%H:%M:%S')}] {m}\n" for m in lines)
                    if self.log_text is not None:
                        self.log_text.configure(state=tk.NORMAL)
                        self.log_text.insert(tk.END, buf)
                        # 行数封顶，避免日志无限增长拖慢控件
                        max_lines = 2000
                        cnt = int(self.log_text.index("end-1c").split(".")[0])
                        if cnt > max_lines:
                            self.log_text.delete("1.0", f"{cnt - max_lines}.0")
                        self.log_text.see(tk.END)
                        self.log_text.configure(state=tk.DISABLED)
                    else:
                        if not hasattr(self, '_log_buffer'):
                            self._log_buffer = []
                        self._log_buffer.extend(f"[{time.strftime('%H:%M:%S')}] {m}\n" for m in lines)
        except Exception:
            pass
        finally:
            self.root.after(120, self._drain_log_queue)

    def log(self, message):
        """兼容旧调用：直接入队（主线程也可调用），由 _drain_log_queue 统一刷新到面板；
        同时持久化到本地日志文件 game_bot.log，便于查看与反馈问题。

        面板与文件写同一份整理后的正文（`log_format.format_body`），时间戳各路由自己的
        加戳方式补齐，所以这里送出去的是不带戳的正文。"""
        body = log_format.format_body(message)
        if not body:
            return
        self._enqueue_log(body)
        try:
            timestamp = time.strftime('%H:%M:%S')
            append_log_file(f'[{timestamp}] {body}\n')
        except Exception:
            _notify_file_write_error(LOG_FILE)
    
    # ===== 配置持久化（load_config / save_config） =====
    def save_config(self):
        """保存配置"""
        # 收集脚本状态
        scripts_config = {}
        for script in self.scripts:
            scripts_config[script.name] = {
                "enabled": script.enabled,
                "params": script.params,
                "last_run_time": script.last_run_time
            }
        self.config["scripts"] = scripts_config
        # 功能列表顺序即执行顺序，随配置持久化，重启后保持用户拖出来的顺序
        self.config["script_order"] = [script.name for script in self.scripts]
        self.config["auto_start_on_launch"] = self.auto_start_on_launch
        self.config["launch_game_on_open"] = self.launch_game_on_open
        self.config["game_launch_delay"] = self.game_launch_delay
        self.config["schedule_time"] = self.schedule_time
        self.config["auto_configure_lineup"] = self.auto_configure_lineup
        self.config["remote_desktop_compat"] = self.remote_desktop_compat
        self.config["restore_cursor_after_click"] = self.restore_cursor_after_click
        
        # 保存到文件
        if save_config(self.config):
            self.log("配置已保存")
        else:
            self.log("保存配置失败")

    def _auto_check_update(self):
        """启动时自动检查更新（后台线程）"""
        def _check():
            import updater
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
            import updater
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
            import updater
            new_path = updater.download_update(download_url)
            if new_path is None:
                self.root.after(0, lambda: self._update_result("下载失败，请检查网络"))
                self.root.after(0, lambda: self.update_btn.configure(text="检查更新", state=tk.NORMAL))
                return
            self.root.after(0, lambda: self._install_and_restart(new_path))

        threading.Thread(target=_download, daemon=True).start()

    def _install_and_restart(self, new_path):
        import updater
        self.update_btn.configure(text="检查更新", state=tk.NORMAL)
        if messagebox.askyesno("下载完成", "更新已下载，是否立即重启应用？"):
            updater.install_and_restart(new_path)

def main():
    # 窗口模式下 sys.stdout 初始为 None，必须尽早接管 print，避免启动期写入 None 崩溃；
    # 早期日志先缓冲，待 GUI 实例创建后灌入面板。
    sys.stdout = _StdoutTee(_early_stdout_sink)
    root = tk.Tk()
    app = GameBotGUI(root)
    # 切换到正式 sink（写面板，调试模式下同时写回真实终端），并补刷早期缓冲
    sys.stdout = _StdoutTee(app._enqueue_log)
    for _m in _early_stdout_buffer:
        with contextlib.suppress(Exception):
            app._enqueue_log(_m)
    _early_stdout_buffer.clear()
    # 启动日志队列节流刷新（主线程 after 循环），避免工作线程高频直冲 Tk 卡顿
    root.after(120, app._drain_log_queue)
    root.mainloop()

if __name__ == "__main__":
    main()