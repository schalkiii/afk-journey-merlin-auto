"""通用能力模块：模板匹配、坐标 IPC、游戏窗口管理。

关键接口：
- find_center(template_path, threshold): 在截图中定位模板中心，未命中返回 None。
- wait_and_click(template_path, name, ...): 轮询等待模板出现并点击，超时则跳过。
- send_coord(x, y): 将坐标写入文件，由 click_from_file.exe(AHK) 读取并执行点击。

设计动机（为什么用「写文件 + AHK 注入」而不是直接 pyautogui 点击）：
本工具与 AutoHotkey 协同工作，点击动作统一交给 AHK 注入，Python 侧只负责
「感知（截图匹配）」与「决策（写坐标）」。坐标文件作为两者间的解耦通道，
避免 Python 内直接模拟输入带来的权限/兼容性抖动。
"""

import contextlib
import ctypes
import hashlib
import os
import random
import shutil
import subprocess
import sys
import threading
import time
from collections import OrderedDict, deque
from ctypes import wintypes

# 子进程一律走「隐藏控制台」封装：本进程是 GUI 子系统（无控制台），裸调
# tasklist / taskkill / powershell 都会各自新建一个黑色 cmd 窗口，见 proc_util。
from proc_util import run_hidden

# 名称映射表已抽到 template_names（纯数据模块）；这里 re-export，保持
# 全仓 `from common import display_name / TEMPLATE_CN` 的导入方式不变。
from template_names import (  # noqa: F401
    ACTION_CN,
    LOG_NAME_MAP,
    TEMPLATE_CN,
    display_name,
)


def _enable_dpi_awareness():
    """按物理像素处理窗口坐标与截图，避免远程桌面/高 DPI 缩放下坐标偏移。

    必须在 pyautogui 首次调用前设置：未声明 DPI 感知时，Windows 会把
    GetClientRect / ClientToScreen 的返回值按缩放比例虚拟化，而屏幕截图仍是
    物理像素，两套坐标混用就会点错位置（远程桌面分辨率/缩放变化时最明显）。
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
    except (AttributeError, OSError):
        with contextlib.suppress(AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


_enable_dpi_awareness()

import cv2
import numpy as np
import pyautogui

APP_DATA_ROOT = os.path.join(os.environ.get("APPDATA", ""), "gamebot")
APP_TEMPLATES_DIR = os.path.join(APP_DATA_ROOT, "templates")
_ACTIVE_TEMPLATES_DIR = None

def get_resource_path(relative_path):
    """获取资源文件的绝对路径，兼容打包后的exe（sys._MEIPASS 指向解压目录）"""
    base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)

def _templates_marker(bundled_dir):
    """对模板目录内所有文件的相对路径+内容摘要做校验（深度校验，逐文件全量 sha256）。"""
    entries = []
    for root, dirs, files in os.walk(bundled_dir):
        dirs.sort()
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, bundled_dir)
            try:
                digest = hashlib.sha256()
                with open(fpath, "rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError:
                continue
            entries.append(f"{rel}:{digest.hexdigest()}")
    return hashlib.sha256("\n".join(entries).encode("utf-8", "surrogatepass")).hexdigest()


# 快速指纹的采样窗口：首尾各取 4KB（文件不足 8KB 时两次读取天然覆盖全文）。
# 459 个模板/5.32MB 的目录做全量 sha256 实测约 0.8–1.1s，而只 stat + 采样读约 10ms，
# 足以把 frozen 启动时的校验开销压到可忽略。代价见 ensure_appdata_templates 的注释。
_TEMPLATE_SAMPLE_BYTES = 4096


def _templates_fast_marker(templates_dir):
    """快速指纹：排序后逐文件记录 `相对路径:大小:首4KB摘要:尾4KB摘要`，再整体 sha256。

    能发现文件缺失、大小变化与采样区内容变化；不读全文，因此对「大小相同且采样区
    未变」的位级差异不敏感——这类损坏需要深度校验（_templates_marker）才能发现。
    """
    entries = []
    for root, dirs, files in os.walk(templates_dir):
        dirs.sort()
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, templates_dir)
            try:
                size = os.path.getsize(fpath)
                digest = hashlib.sha256()
                with open(fpath, "rb") as stream:
                    digest.update(stream.read(_TEMPLATE_SAMPLE_BYTES))
                    if size > _TEMPLATE_SAMPLE_BYTES:
                        stream.seek(max(0, size - _TEMPLATE_SAMPLE_BYTES))
                        digest.update(stream.read(_TEMPLATE_SAMPLE_BYTES))
            except OSError:
                continue
            entries.append(f"{rel}:{size}:{digest.hexdigest()}")
    return hashlib.sha256("\n".join(entries).encode("utf-8", "surrogatepass")).hexdigest()


def _templates_marker_path():
    """快速指纹缓存文件路径；基于 APP_DATA_ROOT 而非写死，便于测试与迁移。"""
    return os.path.join(APP_DATA_ROOT, "templates.marker")


def _read_templates_fast_markers():
    """读取缓存的两行指纹（内置目录、APPDATA 目录）；缺失或格式异常返回 None。"""
    try:
        with open(_templates_marker_path(), encoding="utf-8") as stream:
            lines = [line.strip() for line in stream.read().splitlines() if line.strip()]
    except OSError:
        return None
    if len(lines) != 2:
        return None
    return lines[0], lines[1]


def _write_templates_fast_markers(bundled_marker, appdata_marker):
    """原子写入快速指纹缓存；写失败不影响本次启动，下次会退化为深度校验。"""
    marker_path = _templates_marker_path()
    try:
        os.makedirs(APP_DATA_ROOT, exist_ok=True)
        tmp_path = marker_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as stream:
            stream.write(f"{bundled_marker}\n{appdata_marker}\n")
        os.replace(tmp_path, marker_path)
    except OSError as exc:
        print(f"模板快速指纹写入失败，下次启动将做深度校验: {exc}")


def _is_valid_templates_dir(template_dir, expected_marker=None):
    """验证模板目录是否完整；目录存在但残缺时不能视为可用。"""
    if not os.path.isdir(template_dir):
        return False
    try:
        actual_marker = _templates_marker(template_dir)
    except OSError:
        return False
    return expected_marker is None or actual_marker == expected_marker

def ensure_appdata_templates():
    """
    打包后把内置模板复制到 %APPDATA%\\gamebot\\templates，避免杀软清理
    _MEIPASS 临时目录导致模板文件丢失。启动时先比对快速指纹（约 10ms），
    命中缓存则直接使用 APPDATA 副本；不一致才做全量 sha256 深度校验，
    打包内容变化或副本缺失/损坏时重新复制；复制失败则回退使用内置目录。

    残余风险：快速路径只 stat + 采样首尾 4KB，APPDATA 中「大小不变且采样区不变」
    的位级损坏不会被发现（全量 sha256 才能查出）。要修复这类损坏，需删除
    templates.marker 让下次启动走深度校验，或重新复制模板目录。
    这是 0.8s → ~10ms 的取舍：实际损坏几乎都伴随大小变化或 PNG 数据变化，
    而 PNG 数据变化必然落在采样区。
    """
    global _ACTIVE_TEMPLATES_DIR
    if not getattr(sys, "frozen", False) or not APP_DATA_ROOT:
        _ACTIVE_TEMPLATES_DIR = get_resource_path("templates")
        return
    bundled_dir = get_resource_path("templates")
    if not os.path.isdir(bundled_dir):
        _ACTIVE_TEMPLATES_DIR = None
        return
    try:
        bundled_fast_marker = _templates_fast_marker(bundled_dir)
        if os.path.isdir(APP_TEMPLATES_DIR):
            appdata_fast_marker = _templates_fast_marker(APP_TEMPLATES_DIR)
            cached = _read_templates_fast_markers()
            if cached == (bundled_fast_marker, appdata_fast_marker):
                _ACTIVE_TEMPLATES_DIR = APP_TEMPLATES_DIR
                return

        # 快速指纹不一致（或缺缓存）：退回全量 sha256 深度校验，确认副本是否仍完整。
        marker = _templates_marker(bundled_dir)
        if _is_valid_templates_dir(APP_TEMPLATES_DIR, marker):
            _ACTIVE_TEMPLATES_DIR = APP_TEMPLATES_DIR
            _write_templates_fast_markers(
                bundled_fast_marker, _templates_fast_marker(APP_TEMPLATES_DIR)
            )
            return

        # 先复制到旁路目录并验证，避免目标目录留下半套模板。
        staging_dir = APP_TEMPLATES_DIR + ".staging"
        try:
            if os.path.isdir(staging_dir):
                shutil.rmtree(staging_dir)
            shutil.copytree(bundled_dir, staging_dir)
            if not _is_valid_templates_dir(staging_dir, marker):
                raise OSError("模板缓存校验失败")
            if os.path.isdir(APP_TEMPLATES_DIR):
                shutil.rmtree(APP_TEMPLATES_DIR)
            os.replace(staging_dir, APP_TEMPLATES_DIR)
            _ACTIVE_TEMPLATES_DIR = APP_TEMPLATES_DIR
            _write_templates_fast_markers(
                bundled_fast_marker, _templates_fast_marker(APP_TEMPLATES_DIR)
            )
        except (OSError, ValueError, shutil.Error) as exc:
            # 保留内置目录作为备用；不要让残缺的 APPDATA 目录被选中。
            try:
                if os.path.isdir(staging_dir):
                    shutil.rmtree(staging_dir)
            except OSError:
                pass
            print(f"APPDATA 模板缓存不可用，将回退内置模板目录: {exc}")
            _ACTIVE_TEMPLATES_DIR = bundled_dir
    except (OSError, ValueError, shutil.Error) as exc:
        print(f"APPDATA 模板缓存检查失败，将回退内置模板目录: {exc}")
        _ACTIVE_TEMPLATES_DIR = bundled_dir


def get_templates_dir():
    """模板目录：打包后优先 %APPDATA% 副本，其次内置目录；开发模式返回项目目录"""
    if _ACTIVE_TEMPLATES_DIR and os.path.isdir(_ACTIVE_TEMPLATES_DIR):
        return _ACTIVE_TEMPLATES_DIR
    if getattr(sys, "frozen", False):
        ensure_appdata_templates()
        if _ACTIVE_TEMPLATES_DIR and os.path.isdir(_ACTIVE_TEMPLATES_DIR):
            return _ACTIVE_TEMPLATES_DIR
    return get_resource_path("templates")

def get_template_path(template_name, subdir=None):
    """获取模板图片路径，可指定子目录"""
    if subdir:
        return os.path.join(get_templates_dir(), subdir, template_name)
    return os.path.join(get_templates_dir(), template_name)


# ===== 模板内存缓存（性能）=====
# 同一模板在高频轮询里会被反复读取：每次 cv2.imread + PNG 解码约 1–3ms，而模板内容
# 在运行中几乎不变。此处按 (绝对路径, mtime_ns, size) 缓存解码结果，命中直接返回。
# 约束：返回的是**共享 ndarray**，调用方只读——matchTemplate / resize 都不会原地改
# 模板；若要写入模板像素，必须先 copy，否则会污染所有后续命中。
# key 带 mtime/size 使文件被替换（如 APPDATA 副本重建）后自然失效；读取失败不入缓存。
# GUI 线程与工作线程都可能调用，缓存结构读写加锁；cv2.imread 放在锁外避免长持锁。
_TEMPLATE_CACHE_MAX = 64
_template_cache = OrderedDict()
_template_cache_lock = threading.Lock()


def _template_cache_key(template_path):
    """按 stat 生成缓存键；文件不存在/不可访问时返回 None（跳过缓存）。"""
    try:
        stat = os.stat(template_path)
    except OSError:
        return None
    return (os.path.abspath(template_path), stat.st_mtime_ns, stat.st_size)


def _template_cache_get(cache_key):
    with _template_cache_lock:
        template = _template_cache.get(cache_key)
        if template is not None:
            _template_cache.move_to_end(cache_key)
        return template


def _template_cache_put(cache_key, template):
    with _template_cache_lock:
        _template_cache[cache_key] = template
        _template_cache.move_to_end(cache_key)
        while len(_template_cache) > _TEMPLATE_CACHE_MAX:
            _template_cache.popitem(last=False)


def load_template(template_path):
    """读取模板；运行中发现缓存文件丢失时，修复缓存并重新定位一次。

    命中内存缓存时直接返回共享 ndarray（调用方只读，见上方约束），
    避免高频轮询重复解码 PNG。
    """
    cache_key = _template_cache_key(template_path)
    if cache_key is not None:
        cached = _template_cache_get(cache_key)
        if cached is not None:
            return cached

    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is not None:
        if cache_key is not None:
            _template_cache_put(cache_key, template)
        return template

    # 模板路径是在模块导入时生成的，缓存切换后需要重新生成路径。
    if getattr(sys, "frozen", False):
        relative_name = None
        for base_dir in (APP_TEMPLATES_DIR, get_resource_path("templates")):
            try:
                rel = os.path.relpath(template_path, base_dir)
            except ValueError:
                continue
            if rel != os.pardir and not rel.startswith(os.pardir + os.sep):
                relative_name = rel
                break

        ensure_appdata_templates()
        if relative_name:
            repaired_path = os.path.join(get_templates_dir(), relative_name)
            repaired_key = _template_cache_key(repaired_path)
            if repaired_key is not None:
                cached = _template_cache_get(repaired_key)
                if cached is not None:
                    return cached
            template = cv2.imread(repaired_path, cv2.IMREAD_COLOR)
            if template is not None:
                if repaired_key is not None:
                    _template_cache_put(repaired_key, template)
                return template

    raise ValueError(f"模板读取失败: {template_path}")

ensure_appdata_templates()

def get_work_path(relative_path):
    """获取工作目录下的文件路径（配置文件、日志、坐标 IPC、失败现场等）。

    打包后(sys.frozen)默认以 exe 所在目录为基准，保证数据与 exe 同目录、可持久化。
    2026-11-13 起产物统一放 `dist/`，此时**数据目录仍取上一级（仓库根）**：
    否则 `game_bot_config.json` 读不到（19 项勾选 / 定时 / 任务参数全部回默认）、
    日志改写到 `dist/game_bot.log`、shared 坐标与 debug 现场也跟着分裂成两套。
    判据用「上一级存在 game_bot_config.json」：把 dist/ 单独拷到别处时会自动
    回退到「exe 同目录」的原行为，不影响便携使用。
    """
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
        parent = os.path.dirname(base_path)
        if (os.path.basename(base_path).lower() == "dist"
                and os.path.exists(os.path.join(parent, "game_bot_config.json"))):
            base_path = parent
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)


def get_config_path(relative_path):
    """获取用户可编辑配置的路径：优先工作目录（exe 同目录），不存在才回退打包内置副本。

    `get_resource_path` 在打包后指向 sys._MEIPASS（临时解压目录、只读且可能被杀软清理），
    只适合打包内置的只读资源。阵容 / 迷宫 / 格子映射这类文件用户会直接改 exe 同目录的那份，
    必须走本函数，否则改了不生效。
    """
    work_path = get_work_path(relative_path)
    if os.path.exists(work_path):
        return work_path
    return get_resource_path(relative_path)


# 坐标 IPC 文件：send_coord 写入、click_from_file.exe(AHK) 读取后执行点击
coord_path = get_work_path("shared\\target_coord.txt")
# 单步匹配超时（秒）与轮询间隔（秒），供 wait_and_click 使用
MAX_WAIT = 15
INTERVAL = 0.5

# 调试开关：开启后打印每次匹配的相似度分数，便于校准模板阈值。
# 默认关闭：每帧匹配都会打印一行，高频轮询下会淹没真实日志并徒增队列压力。
PRINT_MATCH_SCORE = False


# ===== 协作式停止（F9 立即停止子脚本） =====
# 上层 GUI 调用 set_stop_checker(stop_event.is_set) 注入停止查询函数。
# 所有子脚本的「感知(screenshot_bgr)」与「动作(send_coord)」都会经过本模块，
# 在这两个底层原语处检查停止标志并抛出 StopRequested，即可穿透打断任何
# 正在运行的子脚本循环，无需逐个改造子脚本。
class StopRequested(BaseException):
    """用户请求停止（F9）。继承 BaseException，避免被子脚本中的
    except Exception 捕获吞掉，确保能一路冒泡到运行循环。"""


_stop_checker = None  # callable() -> bool 或 None


def set_stop_checker(func):
    """注入停止查询函数（返回 True 表示应停止）；传 None 关闭检查。"""
    global _stop_checker
    _stop_checker = func


def check_stop():
    """若已请求停止则抛出 StopRequested。子脚本长循环中也可主动调用。"""
    if _stop_checker is not None and _stop_checker():
        raise StopRequested("用户请求停止 (F9)")


# 截图缓存：匹配/识别频繁且截图变化慢，缓存上一帧避免每次都重新截屏 + 读盘（性能优化）。
# 缓存下沉到 screenshot_bgr 本身，使所有调用方（模板匹配与英雄识别循环）都自动受益；
# 在界面可能发生变化的点击之后调用 invalidate_screenshot_cache 使下一帧为最新。
_screenshot_cache = {"img": None, "ts": 0.0}
SCREENSHOT_CACHE_TTL = 0.05  # 秒；同一帧在极短时间内复用，降低重复截屏开销


# ===== 失败现场逐帧留存 =====
# 任务失败/超时后最需要看的是「当时屏幕上是什么」，而日志往往只剩一行
# 「未识别到 xxx」。这里把最近几帧画面留在环形缓冲里，失败时一次性落盘。
# 缓冲里存的是 numpy 数组引用（不复制大图），只保留最后 DEBUG_FRAME_RING 帧。
DEBUG_CAPTURE_ENABLED = True
DEBUG_CAPTURE_KEEP = 5     # 只保留最近 N 个失败现场目录
DEBUG_FRAME_RING = 5       # 环形缓冲保留的帧数
_frame_ring = deque(maxlen=DEBUG_FRAME_RING)
_frame_ring_lock = threading.Lock()


def _remember_frame(image):
    """把最新一帧放入环形缓冲；缓存命中时是同一个对象，不重复入环。

    缓存命中也必须保证该帧在环里：失败现场要保存的正是「最后一次看到的画面」，
    若只在缓存未命中时记录，连续命中缓存的场景下环里可能是更早的旧帧。
    """
    if not DEBUG_CAPTURE_ENABLED:
        return
    with _frame_ring_lock:
        if _frame_ring and _frame_ring[-1][1] is image:
            return
        _frame_ring.append((time.time(), image))


def screenshot_bgr():
    """截取游戏画面并返回 BGR 格式 numpy 数组（OpenCV 标准色彩顺序）；短 TTL 内复用缓存帧。

    优先使用后台截图（Windows.Graphics.Capture）：游戏被其他窗口遮挡时，
    普通屏幕截图只能拿到遮挡窗口的内容，而 WGC 由 DWM 合成目标窗口画面，
    模板匹配仍然有效。后台截图不可用时自动回退到普通全屏截图。
    返回值仍是「全屏坐标系」下的画面（游戏画面贴在客户区对应位置），
    因此 find_center / 点击坐标语义与之前完全一致。
    """
    check_stop()
    now = time.time()
    if _screenshot_cache["img"] is not None and (now - _screenshot_cache["ts"]) < SCREENSHOT_CACHE_TTL:
        _remember_frame(_screenshot_cache["img"])
        return _screenshot_cache["img"]
    img = _background_screenshot()
    if img is None:
        # 后台截图不可用（依赖缺失/初始化失败）：退回屏幕截图。
        # 此时若游戏不在前台/被遮挡，屏幕截图拿到的是错误画面，必须先确保游戏可见。
        ensure_game_clickable()
        screenshot = pyautogui.screenshot()
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    _screenshot_cache["img"] = img
    _screenshot_cache["ts"] = now
    _remember_frame(img)
    return img


def get_cached_screenshot():
    """返回当前屏幕 BGR 数组（复用截图缓存，等价于 screenshot_bgr）。"""
    return screenshot_bgr()


def invalidate_screenshot_cache():
    """在点击导致界面变化后调用，使下一次截屏拿到最新帧而非缓存旧帧。"""
    _screenshot_cache["img"] = None
    _screenshot_cache["ts"] = 0.0


def _safe_debug_name(task_name):
    """任务名 → 可用作目录名的片段：Windows 路径非法字符与空白统一换成下划线。"""
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(task_name))
    return safe.strip("_") or "task"


def _write_jpeg(path, image):
    """以 JPEG 质量 80 写盘；用编码后二进制写入，兼容含中文任务名的目录。

    cv2.imwrite 在 Windows 遇到非 ASCII 路径会静默返回 False，失败现场目录名带
    中文任务名时帧会「看起来保存了但实际没有」，因此先 imencode 再写文件。
    """
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return False
    with open(path, "wb") as stream:
        stream.write(encoded.tobytes())
    return True


def _prune_failure_dirs(failures_dir):
    """只保留最近 DEBUG_CAPTURE_KEEP 个现场目录；目录名以时间戳开头，按名排序即按时间。"""
    try:
        entries = [
            os.path.join(failures_dir, name)
            for name in os.listdir(failures_dir)
            if os.path.isdir(os.path.join(failures_dir, name))
        ]
    except OSError:
        return
    entries.sort()
    for stale in entries[:-DEBUG_CAPTURE_KEEP]:
        with contextlib.suppress(OSError):
            shutil.rmtree(stale)


def capture_failure_context(task_name, reason, extra=None):
    """把环形缓冲里的最近几帧与失败信息落盘，返回目录；关闭或失败时返回 None。

    目录为 debug/failures/<YYYYMMDD-HHMMSS>_<任务名>/（debug/ 已被 .gitignore 忽略）。
    写入 frame_00.jpg…（JPEG 质量 80，避免 5 张全屏 PNG 占几百 MB）、client.jpg
    （按游戏客户区裁剪的最后一帧）与 meta.txt（时间 / 任务 / 原因 / 客户区 / 附加信息 / 帧时间戳）。
    只保留最近 DEBUG_CAPTURE_KEEP 个现场。任何写入失败都只记日志、绝不上抛：
    留存现场是排查辅助，不能反过来把任务本身搞崩。
    """
    if not DEBUG_CAPTURE_ENABLED:
        return None
    try:
        dest = get_work_path(os.path.join(
            "debug", "failures",
            f"{time.strftime('%Y%m%d-%H%M%S')}_{_safe_debug_name(task_name)}",
        ))
        os.makedirs(dest, exist_ok=True)
        with _frame_ring_lock:
            frames = list(_frame_ring)
        region = game_client_region()
        frame_stamps = []
        for index, (stamp, image) in enumerate(frames):
            frame_stamps.append(
                time.strftime("%H:%M:%S", time.localtime(stamp))
                + f".{int(stamp * 1000) % 1000:03d}"
            )
            if image is not None:
                _write_jpeg(os.path.join(dest, f"frame_{index:02d}.jpg"), image)
        if frames and frames[-1][1] is not None:
            client = _clip_to_region(frames[-1][1], region)
            if client is not None:
                _write_jpeg(os.path.join(dest, "client.jpg"), client)
        meta_lines = [
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"任务: {task_name}",
            f"原因: {reason}",
            f"客户区: {region if region else '未取到游戏窗口'}",
            f"附加信息: {extra if extra else '无'}",
            f"帧时间戳: {', '.join(frame_stamps) if frame_stamps else '无'}",
        ]
        with open(os.path.join(dest, "meta.txt"), "w", encoding="utf-8") as stream:
            stream.write("\n".join(meta_lines) + "\n")
        _prune_failure_dirs(os.path.dirname(dest))
        log(f"已保存失败现场: {dest}")
        return dest
    except (OSError, ValueError, TypeError, RuntimeError, AttributeError, KeyError,
            cv2.error, ctypes.ArgumentError) as exc:
        log(f"保存失败现场失败（已忽略）: {exc}")
        return None


# ===== 模板匹配搜索区域限定（性能）=====
# 桌面分辨率可能远大于游戏窗口（实测双屏 3840x1080 = 4.15MP，而游戏客户区 1600x900 = 1.44MP），
# 全屏 matchTemplate 单次实测 216-357ms；限定到客户区后降到 73-106ms（约 3 倍）。
# 匹配结果仍换算成全屏绝对坐标，因此 send_coord / AHK 一侧的语义完全不变。
GAME_WINDOW_TITLE = "剑与远征：启程"
# 窗口标题关键字：远程桌面/启动器版本可能带后缀，精确标题找不到时按关键字兜底
GAME_WINDOW_KEYWORDS = ("剑与远征：启程", "剑与远征", "启程", "AFK Journey")
_client_region = {"rect": None, "hwnd": None}
_window_handle = {"hwnd": None, "ts": 0.0}

# 游戏客户区尺寸：全部模板与固定点位都按此分辨率采集（登记表见 doc/CLIENT-RESOLUTION.md）。
# 游戏 UI 不随窗口等比缩放，换尺寸时模板 + 偏移常量必须一起重做。
CLIENT_WIDTH = 1600
CLIENT_HEIGHT = 900

# 底部导航带（客户区相对）：主界面「玩法目录」入口与任务面板底部页签
# 都落在这条带内。保守取底部 250px，宁可面积大一点也不要漏判；实机截图后可再收窄。
BOTTOM_BAR_CLIENT_REGION = (0, CLIENT_HEIGHT - 250, CLIENT_WIDTH, 250)


def find_game_window():
    """查找游戏主窗口句柄；优先精确标题，找不到再按关键字枚举可见窗口。"""
    now = time.time()
    cached = _window_handle["hwnd"]
    if cached and now - _window_handle["ts"] < 1.0:
        try:
            if ctypes.windll.user32.IsWindow(cached):
                return cached
        except (AttributeError, OSError):
            pass
    hwnd = None
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, GAME_WINDOW_TITLE)
        if not hwnd:
            found = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def enum_cb(candidate, _lparam):
                if not user32.IsWindowVisible(candidate):
                    return True
                length = user32.GetWindowTextLengthW(candidate)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(candidate, buf, length + 1)
                title = buf.value
                if title and any(key in title for key in GAME_WINDOW_KEYWORDS):
                    found.append(candidate)
                    return False
                return True

            user32.EnumWindows(enum_cb, 0)
            hwnd = found[0] if found else None
    except (AttributeError, OSError):
        hwnd = None
    _window_handle["hwnd"] = hwnd
    _window_handle["ts"] = now
    return hwnd


def _client_rect_of(hwnd):
    """返回客户区绝对矩形 (x, y, w, h)；最小化窗口先还原（不抢焦点，只为恢复渲染）。"""
    try:
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            time.sleep(0.15)
        client = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(client)):
            return None
        if client.right <= 0 or client.bottom <= 0:
            return None
        corner = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(corner)):
            return None
        return (corner.x, corner.y, client.right, client.bottom)
    except (AttributeError, OSError, ctypes.ArgumentError):
        return None


def game_client_region(refresh=False):
    """返回游戏窗口客户区的全屏矩形 (x, y, w, h)；取不到窗口时返回 None 表示应回退全屏。

    每次调用都重新校验窗口位置：远程桌面切换分辨率、用户拖动窗口都会改变客户区，
    沿用旧区域会让模板搜索范围和点击坐标一起偏掉。`refresh` 参数仅为兼容旧调用保留。
    """
    hwnd = find_game_window()
    if hwnd is None:
        _client_region["rect"] = None
        _client_region["hwnd"] = None
        return None
    rect = _client_rect_of(hwnd)
    _client_region["rect"] = rect
    _client_region["hwnd"] = hwnd
    return rect


# ===== 后台截图（Windows.Graphics.Capture）=====
# 游戏被其他窗口遮挡时，普通屏幕截图只能看到遮挡窗口；WGC 由 DWM 直接合成目标窗口
# 画面，即使不在前台/被遮挡也能拿到真实内容。windows-capture 为可选依赖，
# 缺失或初始化失败时自动回退普通截图，不影响原有功能。
_background_capture = {"enabled": True}
_bg_session = {
    "hwnd": None, "session": None, "control": None,
    "frame": None, "frame_ts": 0.0, "error": None, "last_start": 0.0, "warned": False,
}
_bg_composite = {"key": None, "image": None}
_bg_lock = threading.Lock()


def set_background_capture(enabled):
    """开启/关闭后台截图。关闭时释放 WGC 会话，调用方无需关心细节。"""
    _background_capture["enabled"] = bool(enabled)
    if not enabled:
        _stop_background_capture()


def _stop_background_capture():
    with _bg_lock:
        control = _bg_session["control"]
        _bg_session.update({
            "hwnd": None, "session": None, "control": None,
            "frame": None, "frame_ts": 0.0,
        })
        _bg_composite["key"] = None
        _bg_composite["image"] = None
    if control is not None:
        with contextlib.suppress(Exception):
            control.stop()


def _start_background_capture(hwnd):
    now = time.time()
    if now - _bg_session["last_start"] < 2.0:
        return False
    _bg_session["last_start"] = now
    try:
        from windows_capture import WindowsCapture
    except ImportError:
        if not _bg_session["warned"]:
            log("未安装 windows-capture，后台截图不可用，将使用普通屏幕截图")
            _bg_session["warned"] = True
        _bg_session["error"] = "missing"
        return False
    try:
        session = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd)

        @session.event
        def on_frame_arrived(frame, _control):
            frame.convert_to_bgr()
            image = np.array(frame.frame_buffer[:, :, :3], copy=True)
            with _bg_lock:
                _bg_session["frame"] = image
                _bg_session["frame_ts"] = time.time()

        @session.event
        def on_closed():
            with _bg_lock:
                _bg_session["frame"] = None
                _bg_session["frame_ts"] = 0.0

        control = session.start_free_threaded()
        with _bg_lock:
            _bg_session.update({
                "hwnd": hwnd, "session": session, "control": control, "error": None,
            })
        return True
    except (OSError, ValueError, RuntimeError, cv2.error) as exc:
        _bg_session["error"] = str(exc)
        if not _bg_session["warned"]:
            log(f"后台截图初始化失败，将使用普通屏幕截图: {exc}")
            _bg_session["warned"] = True
        return False


def _extended_frame_bounds(hwnd):
    """DWM 可见边框矩形；WGC 画面尺寸与它一致，可据此换算出客户区偏移。"""
    try:
        rect = wintypes.RECT()
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)  # DWMWA_EXTENDED_FRAME_BOUNDS
        )
        if hr == 0 and rect.right > rect.left and rect.bottom > rect.top:
            return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    except (AttributeError, OSError, ctypes.ArgumentError):
        pass
    return None


def _background_client_frame():
    """取最新后台帧并裁剪出客户区，返回 (image, rect)；不可用时返回 None。"""
    if not _background_capture["enabled"]:
        return None
    hwnd = find_game_window()
    if hwnd is None:
        return None
    with _bg_lock:
        current_hwnd = _bg_session["hwnd"]
        has_session = _bg_session["session"] is not None
    if current_hwnd != hwnd or not has_session:
        _stop_background_capture()
        if not _start_background_capture(hwnd):
            return None
        # 首次启动 WGC 需要等待 DWM 送来第一帧
        deadline = time.time() + 1.2
        while time.time() < deadline:
            with _bg_lock:
                if _bg_session["frame"] is not None:
                    break
            time.sleep(0.03)
    rect = game_client_region()
    if rect is None:
        return None
    with _bg_lock:
        frame = _bg_session["frame"]
        frame_ts = _bg_session["frame_ts"]
    if frame is None or time.time() - frame_ts > 10.0:
        return None  # 长时间无新帧（窗口关闭/最小化）：交给普通截图兜底
    frame_h, frame_w = frame.shape[:2]
    _, _, client_w, client_h = rect
    ext = _extended_frame_bounds(hwnd)
    if ext:
        offset_x = rect[0] - ext[0]
        offset_y = rect[1] - ext[1]
    else:
        offset_x = max(0, (frame_w - client_w) // 2)
        offset_y = max(0, frame_h - client_h)
    if offset_x < 0 or offset_y < 0:
        return None
    if frame_h < offset_y + client_h or frame_w < offset_x + client_w:
        return None
    return frame[offset_y:offset_y + client_h, offset_x:offset_x + client_w], rect


def _background_screenshot():
    """把后台截图贴到虚拟全屏画布上，保持与普通截图一致的坐标系。"""
    result = _background_client_frame()
    if result is None:
        return None
    client_img, rect = result
    with _bg_lock:
        frame = _bg_session["frame"]
        frame_ts = _bg_session["frame_ts"]
    cache_key = (id(frame), frame_ts, rect)
    if _bg_composite["key"] == cache_key and _bg_composite["image"] is not None:
        return _bg_composite["image"]
    try:
        user32 = ctypes.windll.user32
        vx = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        vy = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
        vw = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
        vh = user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
        if vw <= 0 or vh <= 0:
            return None
        canvas = np.zeros((vh, vw, 3), dtype=np.uint8)
        x, y, w, h = rect
        canvas[y - vy:y - vy + h, x - vx:x - vx + w] = client_img
    except (ValueError, OSError, ctypes.ArgumentError):
        return None
    _bg_composite["key"] = cache_key
    _bg_composite["image"] = canvas
    return canvas


# ===== 点击前确保游戏窗口位于点击点最上层 =====
# 远程桌面常是单屏：机器人窗口会盖住游戏，直接注入屏幕坐标就点到机器人自己。
# 这里用 WindowFromPoint 判断点击点归属，被遮挡时先把游戏切到前台再点击。
_auto_activate = {"enabled": True, "last_log": 0.0}


def set_auto_activate(enabled):
    """开启/关闭「点击前自动激活游戏窗口」。"""
    _auto_activate["enabled"] = bool(enabled)


def _activate_game_window(hwnd):
    user32 = ctypes.windll.user32
    foreground = user32.GetForegroundWindow()
    current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = False
    try:
        if foreground_thread and foreground_thread != current_thread:
            attached = bool(user32.AttachThreadInput(foreground_thread, current_thread, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if user32.GetForegroundWindow() != hwnd:
            # 前台锁：模拟一次 Alt 键，解除系统对 SetForegroundWindow 的限制
            user32.keybd_event(0x12, 0, 0, 0)
            user32.keybd_event(0x12, 0, 2, 0)
            user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
    finally:
        if attached:
            with contextlib.suppress(Exception):
                user32.AttachThreadInput(foreground_thread, current_thread, False)


def ensure_game_clickable():
    """点击前确保游戏窗口在前台；返回是否**确认**已经在最前（False = 前台锁没解开）。

    True  = 本来就在前台，或激活后已确认到前台；
    False = 尝试激活但 `GetForegroundWindow` 仍不是游戏（Windows 前台锁），
            此时第一次点击会被系统用于激活而吞掉，调用方应改用「点标题栏」等方式补激活；
    None  = 未启用自动激活 / 取不到窗口（调用方按原样继续）。

    2026-11-11 实机回归：旧实现激活后只 sleep(0.25) 就当成功，前台锁下
    SetForegroundWindow 静默失败，于是当天从第一个「邮件」任务起每次点菜单都被吞，
    表现为「点击全部不准」。
    """
    if not _auto_activate["enabled"]:
        return None
    hwnd = find_game_window()
    if hwnd is None:
        return None
    try:
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            time.sleep(0.2)
        if user32.GetForegroundWindow() == hwnd:
            return True
        # 即使点击点属于游戏窗口，只要窗口不在前台，系统也可能把第一次点击用于激活而吞掉：
        # 先显式切前台，保证这次点击一定落到游戏上（实测幻灵入口偶发首次点击丢失）。
        _activate_game_window(hwnd)
        # 激活是异步的，且**可能被前台锁挡下**：轮询确认真的到前台，而不是盲等 0.25 秒
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if user32.GetForegroundWindow() == hwnd:
                break
            time.sleep(0.05)
        now = time.time()
        if now - _auto_activate["last_log"] > 5.0:
            _auto_activate["last_log"] = now
            log("游戏窗口不在前台，已自动切到前台后点击")
        return user32.GetForegroundWindow() == hwnd
    except (AttributeError, OSError, ctypes.ArgumentError):
        return None


def _window_root_at(x, y):
    """返回该屏幕坐标最上层窗口的顶层句柄；取不到返回 None。"""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
        if not hwnd:
            return None
        return user32.GetAncestor(hwnd, 2) or hwnd  # GA_ROOT
    except (AttributeError, OSError, ctypes.ArgumentError):
        return None


def _window_title(hwnd):
    if not hwnd:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(160)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 160)
        return buf.value
    except (AttributeError, OSError, ctypes.ArgumentError):
        return ""


def point_owned_by_game(x, y):
    """点击点是否真的落在游戏窗口上（被浮窗/对话框盖住时返回 False）。"""
    hwnd = find_game_window()
    if hwnd is None:
        return True
    root = _window_root_at(x, y)
    return root is None or root == hwnd



def _resolve_search_region(region=None, client_region=None):
    """把调用方给的搜索范围换算成整屏绝对坐标矩形 (x, y, w, h)。

    region 是整屏绝对坐标，原样返回；client_region 是客户区相对坐标，按当前
    客户区原点换算。两者互斥（同时给会因语义不明而算错坐标，直接拒绝）。
    都不给时退回游戏客户区（取不到则 None = 全屏）。
    无窗口时 client_region 按整屏原点使用，与 region_changed_since 的回退一致。
    """
    if region and client_region:
        raise ValueError("region 与 client_region 互斥")
    if region:
        return region
    if client_region:
        rect = game_client_region()
        if rect:
            return (rect[0] + client_region[0], rect[1] + client_region[1],
                    client_region[2], client_region[3])
        return client_region
    return game_client_region()


def random_sleep():
    """随机等待 2–3 秒：让点击节奏不完全固定，减少被判定为脚本操作的可能。"""
    time.sleep(random.uniform(2.0, 3.0))


def find_center(template_path, threshold=0.8, region=None, client_region=None):
    """在截图中匹配模板，命中则返回其中心坐标 (x, y)，否则返回 None。

    使用 TM_CCOEFF_NORMED：对亮度/对比度变化不敏感，适合游戏 UI 这类
    整体色彩随场景浮动但局部纹理稳定的目标；默认阈值 0.8 在误触与漏触间取折中。
    搜索默认限定在游戏客户区（见 game_client_region），返回值仍是全屏绝对坐标。
    region: 整屏绝对坐标搜索范围；client_region: 客户区相对坐标搜索范围（两者互斥）。
    """
    template = load_template(template_path)
    template_h, template_w = template.shape[:2]

    screenshot = get_cached_screenshot()
    search_region = _resolve_search_region(region, client_region)
    search_area = _clip_to_region(screenshot, search_region)
    if search_area is None:
        return None
    # res 为与搜索区域同尺寸的相关性矩阵，值越大表示越像模板
    match_result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(match_result)

    if PRINT_MATCH_SCORE:
        print(f"{os.path.basename(template_path)} 匹配得分: {max_val:.3f}")

    if max_val < threshold:
        return None

    # max_loc 为模板左上角坐标，加上半宽半高得到中心；限定区域时补偿回全屏坐标
    center_x = max_loc[0] + template_w // 2
    center_y = max_loc[1] + template_h // 2
    if search_region:
        center_x += search_region[0]
        center_y += search_region[1]
    return center_x, center_y


def _clip_to_region(screenshot, region):
    """按 region 裁剪画面；region 为空表示整屏。裁剪后放不下模板时返回 None。"""
    if not region:
        return screenshot
    x = max(0, region[0])
    y = max(0, region[1])
    roi_w = min(region[2], screenshot.shape[1] - x)
    roi_h = min(region[3], screenshot.shape[0] - y)
    if roi_w <= 0 or roi_h <= 0:
        return None
    return screenshot[y:y + roi_h, x:x + roi_w]


def find_center_silent(template_path, threshold=0.8, region=None, timeout=0, interval=0.5,
                       client_region=None):
    """find_center 的静默版本：命中返回中心坐标，否则返回 None，不打印匹配得分。

    与 find_center 的共同点：都支持 region / client_region 限定搜索范围，返回值都是整屏绝对坐标。
    差异（不止「静默」）：本函数额外支持 timeout/interval 轮询等待、client_region 每轮按当前
    窗口矩形重算、以及未命中时刷新一次窗口矩形再试。适合在紧循环里高频调用，
    例如战斗监控、结算弹窗轮询；所有子脚本统一复用本实现以保证 F9 停止检查一致生效。
    region: 限定搜索范围 (x, y, w, h)（整屏绝对坐标）以加快匹配；None 表示用游戏客户区
            （取不到窗口时才退回整屏）。返回值始终是整屏绝对坐标。
    client_region: 客户区相对坐标 (x, y, w, h)，与 region 互斥。窗口可能被拖动，
                  因此每轮循环都按当前客户区原点重新换算。
    timeout: 持续轮询等待模板出现的秒数；0（默认）表示仅检测一次立即返回。
    interval: 轮询间隔（秒）。

    注：push.py 原先自带一份带 timeout 轮询的同名实现，现已统一委托本函数
    （push 内部按调用点显式传 timeout 保留原轮询语义），避免两份逻辑分叉。
    """
    template = load_template(template_path)
    template_h, template_w = template.shape[:2]

    if client_region is not None:
        # 每轮都重算客户区，漏判时无需再走「强制刷新窗口矩形」分支。
        search_region = None
        region_refreshed = True
    else:
        search_region = _resolve_search_region(region)
        region_refreshed = False
    start_time = time.time()
    while True:
        check_stop()
        if client_region is not None:
            search_region = _resolve_search_region(client_region=client_region)
        screenshot = get_cached_screenshot()
        search_area = _clip_to_region(screenshot, search_region)
        if search_area is None:
            return None
        if search_area.shape[0] < template_h or search_area.shape[1] < template_w:
            return None
        match_result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)

        _, max_val, _, max_loc = cv2.minMaxLoc(match_result)
        if max_val >= threshold:
            # max_loc 为模板左上角坐标，加上半宽半高得到中心；region 裁剪需补偿偏移
            center_x = max_loc[0] + template_w // 2
            center_y = max_loc[1] + template_h // 2
            if search_region:
                center_x += search_region[0]
                center_y += search_region[1]
            return center_x, center_y

        # 限定区域后漏判的首要原因是用户在运行中拖动了窗口：刷新一次窗口矩形再试，
        # 取不到窗口时会自动退化为整屏匹配，行为与限定前一致。
        # 矩形没变时重匹配必然还是同一结果，直接进入超时判断，省一次 matchTemplate
        # 与一次截图（高频轮询下这是主要的固定浪费）。
        if region is None and not region_refreshed:
            region_refreshed = True
            previous_region = search_region
            search_region = game_client_region(refresh=True)
            if search_region != previous_region:
                continue

        if timeout <= 0:
            return None
        remaining = timeout - (time.time() - start_time)
        if remaining <= 0:
            return None
        # 不能睡满 interval：timeout=0.25、interval=0.5 时睡过 deadline 会拖慢调用方
        time.sleep(min(interval, remaining))


def click_blank_to_exit():
    """点击屏幕空白区域以关闭弹窗/退出阵容视图的兜底手段。

    当「点击空白处关闭」(dianjikongbaichuguanbi) 模板检测不到时使用：
    游戏弹窗背后通常是可点击的半透明遮罩，点击远离弹窗中心的空白处即可关闭。
    这里点击屏幕**左下角**空白区：底部居中位置与多个面板的主操作按钮重合
    （结社战线「扫荡」、狩猎悬赏「搜寻精怪」、愿望单「交付」都在底部居中一带），
    兜底点击若落在那里，会在关弹窗的同时误触发按钮。
    """
    region = game_client_region()
    if region:
        x, y, w, h = region
        send_coord(int(x + w * 0.12), int(y + h * 0.8))
    else:
        h, w = screenshot_bgr().shape[:2]
        send_coord(int(w * 0.12), int(h * 0.8))
    time.sleep(0.5)


def dismiss_popup():
    """关闭游戏内弹窗（礼包广告 / 结算 / 战斗失败提示等）的兜底。

    优先按「点击空白处关闭」提示定位、并点它左上方的空白处（避开热区避免误触按钮）；
    若检测不到该提示，则点击屏幕左下空白处兜底。供任务切换（清理上一任务残留弹窗）
    与战斗任务失败清理复用，避免弹窗卡死后续流程。
    """
    if dismiss_popup_away_from():
        return True
    # 模板检测不到时点击屏幕空白处兜底（兼容礼包广告等非标准弹窗）
    click_blank_to_exit()
    return True


def at_main_interface(threshold=0.8):
    """主界面判据：底部「玩法目录」可见，**且没有任何返回箭头**。

    只看 wanfamulu 会被骗：英雄厅堂 / 玩法目录子页的底部栏里有同一个图标。
    2026-11-04 实测——任务停在英雄厅堂时 `recover_to_main_interface()` 判定
    「已在主界面」直接返回，随后按 HUD 坐标点击的赛季手册 / 月桂之旅 / 当前进度
    三个入口全部落空。主界面本身不显示返回箭头，用它把子页区分出来。
    """
    if not find_center_silent(get_template_path("wanfamulu.png"), threshold,
                              client_region=BOTTOM_BAR_CLIENT_REGION):
        return False
    for back_template in ("exitck.png", "fanhui.png"):
        if find_center_silent(get_template_path(back_template), threshold):
            return False
    return True


# 「巅峰联赛」活动介绍页遮挡主界面时的兜底点位（客户区相对坐标）。
# 该页没有关闭按钮，只能先点卡片外的模糊背景尝试退出；仍不消失就点「进入巅峰联赛」
# 进活动页，再由 recover_to_main_interface 的 exitck/exit 逐层退回。
# 卡片横跨 x≈340–1270，故左侧 150 一定落在卡片外。
PROMO_OUTSIDE_POS = (150, 450)


def open_wanfamulu(threshold=0.7, timeout=8, max_attempts=2):
    """打开玩法目录并用面板左上角标题自证，返回是否已打开。

    首次点击常被系统用于激活窗口而吞掉：2026-11-07 实测同一坐标点第一次无效、
    第二次才打开（日志表现为「命中 玩法目录」之后卡片连续 8~15 秒全部匹配不到）。
    点击后先确认标题（仅目录页出现，主界面/愿望单实测最高 0.58），未打开则补点一次，
    避免整条流程白等到超时。
    """
    for attempt in range(1, max_attempts + 1):
        if not wait_and_click(get_template_path("wanfamulu.png"), "wanfamulu", threshold,
                              client_region=BOTTOM_BAR_CLIENT_REGION, timeout=timeout):
            return False
        if find_center_silent(get_template_path("wanfamulubiaoti.png"), 0.8, timeout=3.0):
            return True
        if attempt < max_attempts:
            log(f"玩法目录未打开（第 {attempt} 次点击可能被窗口激活吞掉），补点一次")
    log("玩法目录未打开，无法进入目标玩法")
    return False


def recover_to_main_interface(max_tries=8):
    """兜底回主界面：任务卡在某界面（弹窗 / 子界面）反复检测不到目标时使用。

    依次尝试点击「点击空白处关闭」(dianjikongbaichuguanbi)、tuichulibao（退出礼包）、
    exitck、exit（返回上一层），逐层从卡住处退出，直到 `at_main_interface()` 成立。
    「巅峰联赛」活动介绍页没有关闭按钮，单独用「点卡片外空白 → 点进入按钮」处理。
    无任何退出按钮时点击屏幕空白处兜底。供 wait_and_click 的兜底恢复与
    任务切换前的 ensure_main_interface 复用，避免把游戏停在中间界面导致后续任务卡死。
    """
    tpl_exit = get_template_path("exit.png")
    tpl_close = get_template_path("dianjikongbaichuguanbi.png")
    tpl_tuichulibao = get_template_path("tuichulibao.png")
    tpl_exitck = get_template_path("exitck.png")
    tpl_promo = get_template_path("dianfengliansai.png")
    # 退出按钮尝试顺序：先关弹窗（空白关闭 / 退出礼包 / exitck），再返回上一层
    exit_templates = [tpl_close, tpl_tuichulibao, tpl_exitck, tpl_exit]
    promo_outside_tried = False

    for _ in range(max_tries):
        check_stop()
        if at_main_interface():
            return True
        # 2026-11-06 失败现场：活动介绍页盖住主界面时模板全被遮挡，逐层退出点不到任何按钮。
        # 该页无关闭按钮，先试「点卡片外空白关闭」；仍在则点「进入巅峰联赛」进活动页，
        # 由后续轮次用 exitck/exit 退出活动页，避免停在介绍页让整个任务失败。
        promo_pos = find_center_silent(tpl_promo, 0.8)
        if promo_pos:
            if promo_outside_tried:
                click_position(promo_pos, wait=2.0, twice=False)
            else:
                promo_outside_tried = True
                region = game_client_region()
                origin_x, origin_y = (region[0], region[1]) if region else (0, 0)
                click_position(
                    (origin_x + PROMO_OUTSIDE_POS[0], origin_y + PROMO_OUTSIDE_POS[1]),
                    wait=1.5, twice=False,
                )
            continue
        clicked = False
        for tpl in exit_templates:
            pos = find_center_silent(tpl, 0.8)
            if pos:
                send_coord(*pos)
                time.sleep(1.5)
                clicked = True
                break
        if not clicked:
            # 没有任何退出按钮：点击屏幕空白处兜底，尝试关闭遮挡弹窗
            click_blank_to_exit()
            time.sleep(1.0)
    return at_main_interface()


def ensure_main_interface():
    """任务切换前的兜底：先关闭残留弹窗，若仍未在主界面则逐层退出回到主界面。

    返回 True 表示已处于（或已回到）主界面。供运行循环在每个任务开始前调用，
    确保上一任务卡在子界面时，本次入口检测能正常进行，不连锁卡死后续任务。
    判据用 `at_main_interface()`（玩法目录可见 **且** 无返回箭头），
    否则停在英雄厅堂这类底部同样有玩法目录图标的子页时会被误判为已回主界面。
    """
    dismiss_popup()
    if at_main_interface():
        return True
    return recover_to_main_interface()


def try_auto_configure_lineup(threshold=0.8, retries=3):
    """在挑战/战斗开始前尝试自动采用系统「通关阵容」：

    ①检测通关阵容入口(tongguanzhenrong)并点击，展开推荐阵容；
    ②检测一键采用(yijiancaiyong)并点击，套用该阵容。
    目的：省去手动布阵；未找到入口则直接跳过(返回 False)，不影响后续挑战流程。

    健壮性：
    - 重试多次(retries)：挑战界面刚进入时可能仍在加载/动画，单次检测易漏，
      故在每次尝试之间短暂等待后重试，提高匹配成功率。
    - 若展开后找不到一键采用，则依次尝试「点击空白处关闭」(dianjikongbaichuguanbi)，
      仍找不到再点击屏幕空白处兜底，确保退出阵容视图、不卡死。
    """
    tpl_lineup = get_template_path("tongguanzhenrong.png")
    tpl_adopt = get_template_path("yijiancaiyong.png")
    # 展开展示阵容后用于退出的「点击空白处关闭」按钮（与其他 flow 脚本一致）
    tpl_blank_close = get_template_path("dianjikongbaichuguanbi.png")

    for _attempt in range(retries):
        # 优先：当前界面已直接出现「一键采用」，直接采用（最常见的推荐阵容挂件）
        adopt_pos = find_center_silent(tpl_adopt, threshold)
        if adopt_pos:
            send_coord(*adopt_pos)
            time.sleep(1.0)
            return True

        # 否则尝试展开「通关阵容」入口，再寻找一键采用
        entry_pos = find_center_silent(tpl_lineup, threshold)
        if entry_pos:
            send_coord(*entry_pos)
            time.sleep(1.0)
            adopt_pos = find_center_silent(tpl_adopt, threshold)
            if adopt_pos:
                send_coord(*adopt_pos)
                time.sleep(1.0)
                return True
            # 展开后未找到一键采用：依次尝试「点击空白处关闭」→ 点击屏幕兜底退出阵容视图
            blank_close_pos = find_center_silent(tpl_blank_close, threshold)
            if blank_close_pos:
                send_coord(*blank_close_pos)
                time.sleep(0.5)
            else:
                click_blank_to_exit()
            return False

        # 两种入口都未找到：稍候界面稳定后重试（应对刚进入挑战界面的加载延迟）
        log("未检测到通关阵容入口，重试中...")
        time.sleep(0.6)

    return False

class ClickerNotRunning(RuntimeError):
    """click_from_file.exe 已退出，坐标不再被消费——点击全部落空。"""



CLICKER_MISS_LIMIT = 3
_clicker_miss = {"streak": 0}
# 会话不一致告警只检查一次：send_coord 每次调用都 Tasklist 开销大，且刷屏无意义
_session_warn = {"checked": False, "done": False}

# 点击后把鼠标放回原处：click_from_file 会把光标留在目标点，连续批处理会一直「拽着」
# 用户的鼠标。窗口消息注入（PostMessage/SendMessage）实测被本游戏忽略，做不到零打扰，
# 因此这里至少让光标即刻归位；焦点仍会被 ensure_game_clickable 激活一次。
_restore_cursor = {"enabled": True}


def set_restore_cursor(enabled):
    """开关「点击后归还鼠标位置」。"""
    _restore_cursor["enabled"] = bool(enabled)


def _read_cursor_pos():
    """读当前光标位置；拿不到返回 None（非 Windows 或调用失败）。"""
    point = wintypes.POINT()
    if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        return point.x, point.y
    return None


def _restore_cursor_pos(pos):
    """把光标放回 pos。调用方需先等点击器完成移动，否则会被它再次覆盖。"""
    if pos:
        ctypes.windll.user32.SetCursorPos(int(pos[0]), int(pos[1]))


def _ahk_script_running():
    """确认 AutoHotkey64.exe 跑的是本项目的 click_from_file.ahk（不是用户别的 AHK）。

    tasklist 只看进程名会误判：用户自己开了 AHK 也会显示 AutoHotkey64.exe。
    查一次命令行（仅启动时调用，开销可接受）；查询失败时保守认为在运行。
    """
    try:
        result = run_hidden(
            ["powershell", "-NoProfile", "-Command",
             ("Get-CimInstance Win32_Process -Filter \"Name='AutoHotkey64.exe'\" "
              "| Select-Object -ExpandProperty CommandLine")],
            capture_output=True, timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    out = (result.stdout or b"").decode("utf-8", errors="ignore").strip()
    if not out:
        # 提权进程的 CommandLine 常读不到（实测 2026-11-10 为空）：保守按在跑处理，
        # 避免把正常注入器误判成「已退出」。
        return True
    return "click_from_file.ahk" in out


def clicker_process_alive():
    """只读探测点击注入器进程是否在（编译 exe 或 AHK v2 明文脚本，二选一）。"""
    try:
        # 不用 text=True：中文 Windows 上 tasklist 输出 GBK，UTF-8 解码会抛错并让
        # stdout 变成 None（2026-11-08 实机踩过）。进程名是 ASCII，直接比对 bytes。
        result = run_hidden(["tasklist", "/NH"], capture_output=True,
                            timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        # 探测本身失败时按存活处理，交给 send_coord 判定，避免误中止整轮任务
        return True
    out = result.stdout or b""
    if b"click_from_file.exe" in out:
        return True
    if b"AutoHotkey64.exe" in out:
        return _ahk_script_running()
    return False


def clicker_alive():
    """只读探测 click_from_file.exe 是否仍在运行，不产生任何点击副作用。

    旧实现把当前光标位置当哨兵写进坐标 IPC 文件、等点击器消费；消费本身是一次真实
    点击，若用户光标停在别的窗口上就会被误点。改为 tasklist 进程探测，
    `send_coord` 的连续未消费计数继续作为第二道保险。
    2026-11-10 起兼容 AHK v2 明文脚本（click_from_file.ahk）注入器。
    """
    if os.path.exists(coord_path):
        return False   # 上一条坐标都没人取走，必然没在运行
    return clicker_process_alive()


# ===== 会话一致性：注入器必须和游戏在同一个 Windows 会话 =====
# 2026-11-12 冷启动实测：注入器被上一个会话（RDP-Tcp#1，session 3）启动并留在那里，
# 而游戏在 Console（session 1）。注入器照常读走坐标文件、SendInput 却打在自己会话的
# 桌面上——文件消失（判据说「点击成功」）、游戏毫无反应。**坐标文件的消费状态无法区分
# 这两种情况**，只能比较进程所属会话。
def _pid_session_id(pid):
    """返回进程所属的 Windows 会话 ID；取不到返回 None。"""
    if not pid:
        return None
    try:
        sid = ctypes.c_ulong()
        if not ctypes.windll.kernel32.ProcessIdToSessionId(int(pid), ctypes.byref(sid)):
            return None
        return int(sid.value)
    except (AttributeError, OSError, ctypes.ArgumentError):
        return None


def current_session_id():
    """当前进程所在的会话 ID。"""
    return _pid_session_id(os.getpid())


def is_process_elevated():
    """当前进程是否以管理员身份运行。

    为什么必须查这一条：游戏以管理员启动时，非提权进程的 `SendInput` 会被 UIPI
    静默丢弃——注入器照常读走坐标文件（「坐标被消费 == 点击成功」的判据全部成立），
    游戏画面却一动不动，最后表现为**每个任务都超时失败**，日志里找不到任何异常
    （2026-11-12 实测：同一份代码，普通权限跑全失败，管理员跑立刻正常交付）。
    """
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def game_window_session_id():
    """游戏窗口所属进程的会话 ID；取不到返回 None。"""
    hwnd = find_game_window()
    if hwnd is None:
        return None
    try:
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return _pid_session_id(pid.value)
    except (AttributeError, OSError, ctypes.ArgumentError):
        return None


def _clicker_session_ids():
    """列出所有在跑的点击注入器进程的会话 ID。"""
    try:
        result = run_hidden(["tasklist", "/NH"], capture_output=True,
                            timeout=3, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    out = result.stdout or b""
    names = []
    if b"click_from_file.exe" in out:
        names.append("click_from_file.exe")
    if b"AutoHotkey64.exe" in out:
        names.append("AutoHotkey64.exe")
    sids = []
    for name in names:
        try:
            listing = run_hidden(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                                 capture_output=True, timeout=3, check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        # 逐行解析 "名字","PID","会话名","会话号","内存"
        for raw in (listing.stdout or b"").decode("gbk", errors="ignore").splitlines():
            parts = [p.strip('"') for p in raw.split('","')]
            if len(parts) >= 4 and parts[1].isdigit():
                try:
                    sids.append(int(parts[3]))
                except ValueError:
                    continue
    return sids


def clicker_session_mismatch():
    """注入器与游戏不在同一会话时返回说明文字，正常返回 None。

    2026-11-13 修正结论强度：会话不一致**不是**点击失效的充分条件。11-12 那次
    「游戏毫无反应」是同时改了「杀掉旧注入器 + 提权重启」两个变量，功劳被误记到
    会话上；11-13 实测注入器在会话 3、游戏在会话 1，19 项任务里 17 项点击正常生效。
    真正会让 SendInput 被静默丢弃的是**非提权进程对提权游戏**（UIPI），见
    `is_process_elevated()`。这里只作为排查线索，不再断言「游戏不会有任何反应」。
    """
    game_sid = game_window_session_id()
    if game_sid is None:
        return None
    sids = _clicker_session_ids()
    if not sids:
        return None
    if game_sid in sids:
        return None
    return (f"点击注入器运行在会话 {','.join(str(s) for s in sorted(set(sids)))}，"
            f"游戏在会话 {game_sid}：若出现点击不生效，请优先确认本工具与注入器"
            f"均已提权，再考虑会话因素")


def log_clicker_session_warning():
    """会话不一致时记一条日志（每个进程只检查一次，避免每次点击都 Tasklist）。"""
    if _session_warn["checked"]:
        return
    _session_warn["checked"] = True
    note = clicker_session_mismatch()
    if note is None:
        return
    _session_warn["done"] = True
    log(f"提示: {note}")


def _write_coord_raw(x, y, wait_timeout=1.5):
    """把坐标写入 IPC 并等注入器消费完成；返回 True 表示注入器已处理（点击已执行）。

    只负责「写 + 等」，不含激活窗口、光标归位等前置动作，供 send_coord 与
    `_click_title_bar` 共用（后者需要绕过 send_coord 自身的前置逻辑）。
    """
    wait_count = 0
    while os.path.exists(coord_path) and wait_count < 20:
        check_stop()  # 若 AHK 迟迟未消费上一条坐标，允许 F9 在此期间中断
        time.sleep(0.05)
        wait_count += 1

    with open(coord_path, "w", encoding="utf-8") as f:
        f.write(f"{x} {y}")

    deadline = time.time() + wait_timeout
    while os.path.exists(coord_path):
        check_stop()
        if time.time() >= deadline:
            break
        time.sleep(0.02)
    return not os.path.exists(coord_path)


def _click_title_bar():
    """点窗口标题栏把游戏真正激活；标题栏不属于客户区，不会触发任何游戏内操作。

    Windows 前台锁下 `SetForegroundWindow` 会静默失败，此时第一次点击会被系统用于
    激活而吞掉——直接点游戏里的按钮就会「点了没反应」。用标题栏这一下先完成激活，
    随后的目标点击才稳定落地。无标题栏（全屏无边框）时不做这件事，避免误触游戏画面。
    """
    hwnd = find_game_window()
    if hwnd is None:
        return False
    try:
        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        client = _client_rect_of(hwnd)
        if not client:
            return False
        cx, cy, cw, _ch = client
        title_h = cy - rect.top
        if title_h < 12:
            return False   # 没有标题栏：不要拿游戏画面当激活区
        if not _write_coord_raw(cx + cw // 2, rect.top + title_h // 2, wait_timeout=1.0):
            return False
        time.sleep(0.35)
        return True
    except (AttributeError, OSError, ctypes.ArgumentError):
        return False


def send_coord(x, y):
    """将待点击坐标写入 IPC 文件，等待 AHK 消费完成后返回。

    先自旋等待上一条坐标被消费（文件消失），避免 AHK 尚未读取就被覆盖；
    写入后等待 AHK 读走本次坐标（文件被删除）再返回，替代原先无条件 0.5s 睡等——
    既更快（命中即返回），又更稳健（确保点击已发生）。期间 check_stop 允许 F9 中断。

    click_from_file.exe 会在长时间运行后自行退出，此后所有点击都会静默落空、界面表现为
    「连续多轮无变化」。因此连续 CLICKER_MISS_LIMIT 次坐标无人消费即抛 ClickerNotRunning，
    让调用方立即失败并报出真实原因，而不是空转到各流程自己的超时上限。

    2026-11-11 增加两处前置校验（当天「点击全部不准」的直接原因是第 1 条）：
    1. `ensure_game_clickable()` 返回 False（前台锁没解开）时，先用标题栏点击激活，
       否则这一次点击会被系统用于激活而吞掉；
    2. 点击点被其它窗口盖住时记日志（含遮挡窗口标题），便于事后定位，
       不再悄悄把点击发给别的窗口。
    """
    check_stop()
    log_clicker_session_warning()
    if ensure_game_clickable() is False and _click_title_bar():
        log("前台锁未解开，已用标题栏点击激活窗口后再点目标")
    if not point_owned_by_game(x, y):
        root = _window_root_at(x, y)
        log(f"点击点被其它窗口遮挡：({x},{y}) 属于「{_window_title(root)}」")

    cursor_before = _read_cursor_pos() if _restore_cursor["enabled"] else None
    consumed = _write_coord_raw(x, y)

    if not consumed:
        _clicker_miss["streak"] += 1
        if _clicker_miss["streak"] >= CLICKER_MISS_LIMIT:
            _clicker_miss["streak"] = 0
            log("点击注入未生效：click_from_file.exe 可能已退出，请重启程序或检查杀软拦截")
            raise ClickerNotRunning("click_from_file.exe 未在消费坐标")
    else:
        _clicker_miss["streak"] = 0

    if cursor_before is not None:
        # 旧 exe 在读走坐标后还要 MouseMove + Sleep(80~260ms) + Click 才真正完成，
        # 过早归位会和它抢光标（用户看到的「鼠标来回横跳」，偶发点击落空）。
        # 等 0.35s 覆盖旧实现的最坏时序；新脚本虽已完成，多等也无害。
        time.sleep(0.35)
        # 目标点本来就贴近原位时不必再动一次光标，减少一次可见跳动
        if abs(cursor_before[0] - x) > 3 or abs(cursor_before[1] - y) > 3:
            _restore_cursor_pos(cursor_before)



def click_position(pos, wait=1.5, twice=True):
    """点击模板匹配得到的全屏坐标并等待界面响应；pos 为 None 时什么都不做（返回 False）。

    游戏未处于前台时，第一次鼠标事件会被系统用于激活窗口而被吞掉，故默认连点两次
    （间隔 0.25 秒）：窗口已激活时两次点击等价，未激活时第二次才真正生效。
    跳转类按钮（进面板 / 开战 / 下一层）请传 twice=False——连点会「进入后又退出」。
    """
    if pos is None:
        return False
    send_coord(pos[0], pos[1])
    invalidate_screenshot_cache()
    if twice:
        time.sleep(0.25)
        send_coord(pos[0], pos[1])
        invalidate_screenshot_cache()
    time.sleep(wait)
    return True


def click_and_confirm(template_path, name, confirm, *, attempts=2, threshold=0.8,
                      find_timeout=4.0, confirm_timeout=6.0):
    """点击跳转型按钮，并校验界面真的切换了；没切过去就补点，最多 attempts 轮。

    「模板命中 + 发送点击」只证明点到了像素，不证明点击生效：窗口不在前台时第一次
    鼠标事件会被系统吞掉用于激活窗口，弹窗遮挡时点击也会落空。2026-11-10 日志里
    「点了塔卡片却仍停在玩法目录、后续按钮 15 秒都等不到」「点社交没进好友面板」
    都是这个原因——旧实现把 send_coord 返回当成成功，于是一路错下去。

    这里把「点击 → 轮询 confirm → 未生效则补点」收敛成一处，跳转类入口统一用它：
    每次只点一下（twice=False 的效果），确认失败才点第二下，避免「进入后又退出」。

    confirm 必须是无参回调，且判据要选「目标页面独有」的元素（按钮/标题），不要用
    「当前页面消失」——加载动画期间两者都不成立，会误判。
    """
    prefix = display_name(name)
    if confirm():
        return True
    for attempt in range(1, attempts + 1):
        check_stop()
        pos = find_center_silent(template_path, threshold, timeout=find_timeout)
        if pos is None:
            log(f"{prefix}：第 {attempt} 次没找到按钮，无法点击")
            return False
        click_position(pos, wait=0.6, twice=False)
        deadline = time.time() + confirm_timeout
        while time.time() < deadline:
            check_stop()
            if confirm():
                return True
            time.sleep(0.5)
        log(f"{prefix}：第 {attempt} 次点击后未确认界面切换（首次点击可能被激活吞掉），补点")
    return False


def _drag_scroll(x1, y1, x2, y2, steps=25, step_sleep=0.02):
    """SendInput 逐步拖动（按住左键 + 逐步移动），用于 ScrollRect 类列表滚动。

    AHK 的 send_drag 是瞬移式拖拽，Unity 的 ScrollRect 不认（2026-11-08 实测：卡片
    列表纹丝不动）；必须「按住 + 逐步移动 + 松开」才触发滚动。仅用于拖拽滚动，不用于
    点击。try/finally 保证 LEFTUP 一定执行，避免进程中断卡住左键。
    注意：目标窗口是管理员进程时，本进程也必须有管理员权限（项目本来就要求）。
    """
    INPUT_MOUSE = 0
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INPUT(ctypes.Structure):
        class _I(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]

        _anonymous_ = ("i",)
        _fields_ = [("type", wintypes.DWORD), ("i", _I)]

    def _send(flags):
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(0, 0, 0, flags, 0, None)
        return ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    ctypes.windll.user32.SetCursorPos(int(x1), int(y1))
    time.sleep(0.15)
    _send(MOUSEEVENTF_LEFTDOWN)
    try:
        for step in range(1, steps + 1):
            x = x1 + (x2 - x1) * step / steps
            y = y1 + (y2 - y1) * step / steps
            ctypes.windll.user32.SetCursorPos(int(x), int(y))
            time.sleep(step_sleep)
    finally:
        _send(MOUSEEVENTF_LEFTUP)
    time.sleep(0.3)


def scroll_in_client_region(direction="down", distance_ratio=0.35, times=1, region=None):
    """在卡片列表内做**逐步拖动**滚动，露出下方卡片。

    direction="down" 表示「露出更下面的内容」：鼠标从列表下部往上部拖，内容跟随上移。
    region: 可选 (x, y, w, h) 全屏绝对坐标滚动区；缺省按玩法目录卡片列表比例取。
    2026-11-08 实测链路：①滚轮（mouse_event / SendInput）确实能滚，但滚到底后第三行
    标题被底部页签栏遮挡、模板匹配不到；②按住上拖能把列表拖到「标题露出」的位置，
    但必须是逐步拖动（见 _drag_scroll），AHK 的瞬移式 send_drag 无效；③卡片图案区
    不可点，按钮在标题区，所以必须拖到标题可见再点。
    拖拽后若目录标题消失（误入卡片详情），点返回箭头退回目录。
    """
    client = game_client_region()
    if client is None:
        return False
    origin_x, origin_y, width, height = client

    if region is not None:
        reg_x, reg_y, reg_w, reg_h = region
        anchor_x = reg_x + reg_w // 2
        if direction == "down":
            start_y = reg_y + int(reg_h * 0.80)
            end_y = reg_y + int(reg_h * 0.25)
        else:
            start_y = reg_y + int(reg_h * 0.25)
            end_y = reg_y + int(reg_h * 0.80)
    else:
        # 拖动列与起止：以**首张卡片中心**为基准上下各 120px（2026-11-08 实机验证成功的
        # 范围：起点在列表内、终点在列表上部；固定比例起止会落在卡片上或列表外，拖不动）。
        anchor_x = origin_x + width // 2
        anchor_y = origin_y + int(height * 0.5)
        for name in ("guajiguanqia.png", "mimengzhiyu.png", "pujing.png",
                     "nvshenta.png", "pata.png"):
            pos = find_center_silent(get_template_path(name), 0.8, timeout=0)
            if pos:
                anchor_x = pos[0]
                anchor_y = pos[1]
                break
        if direction == "down":
            start_y = anchor_y + 120
            end_y = anchor_y - 120
        else:
            start_y = anchor_y - 120
            end_y = anchor_y + 120

    for _ in range(max(1, times)):
        check_stop()
        _drag_scroll(anchor_x, start_y, anchor_x, end_y)
        time.sleep(1.0)
        invalidate_screenshot_cache()
        # 护栏（仅玩法目录场景）：拖动松开点若仍落在卡片上会进卡片详情，此时目录标题消失。
        # 指定 region 的调用方（如悬赏卡片网格）不在目录里，跳过该检查。
        if region is None and \
                find_center_silent(get_template_path("wanfamulubiaoti.png"), 0.8, timeout=0) is None:
            back_pos = (find_center_silent(get_template_path("exit.png"), 0.8, timeout=0)
                        or find_center_silent(get_template_path("exitck.png"), 0.8, timeout=0))
            if back_pos:
                click_position(back_pos, wait=1.5, twice=False)
    return True


def is_loading_screen(brightness_threshold=35.0):
    """判断当前是否是游戏加载画面（近似全黑、底部显示「加载中…」）。

    2026-11-09 实机：女神塔回退时停在「加载中…」，2 秒内看不到扫荡按钮就被判失败；
    加载画面客户区中央平均亮度实测很低，正常界面远高于此，用亮度做判据不需要新模板。
    """
    img = screenshot_bgr()
    region = game_client_region()
    if region is None:
        return False
    origin_x, origin_y, width, height = region
    center = img[origin_y + int(height * 0.2):origin_y + int(height * 0.8),
                 origin_x + int(width * 0.2):origin_x + int(width * 0.8)]
    if center.size == 0:
        return False
    return float(center.mean()) < brightness_threshold


def wait_until_loaded(timeout=15.0, poll=0.5):
    """等加载画面结束；返回 True 表示已不是加载态（或本来就正常），超时仍在加载返回 False。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        check_stop()
        if not is_loading_screen():
            return True
        time.sleep(poll)
    return not is_loading_screen()


# ===== 冷启动：等游戏真正可操作再跑任务 =====
# 从「点了快捷方式」到「画面能跑模板匹配」的默认上限。实测这台机器冷启动约 1 分半
# （启动器拉起本体 → 资源校验/更新 → 开始界面），180 秒留足余量。
GAME_READY_TIMEOUT = 180.0
GAME_READY_POLL = 1.0
# 客户区尺寸容差：全套模板按 1600×900 采集，尺寸不符时匹配会整体偏移几个像素，
# 于是「页签/按钮明明在却匹配不到」。窗口在启动动画期间会短暂变化，故要等它稳定。
CLIENT_SIZE_TOLERANCE = 8

# 「游戏本体已经可以操作」的正向标志：只要命中任意一个，就说明已经越过资源校验/加载。
# 覆盖四种合法落点：开始界面、主界面 HUD、以及两类只可能出现在可交互弹窗上的元素。
GAME_READY_MARKERS = (
    ("开始界面", "start.png"),
    ("主界面", "wanfamulu.png"),
    ("可交互弹窗", "dianjikongbaichuguanbi.png"),
    ("月卡奖励", "yuekajiangli.png"),
    ("礼包弹窗", "libao.png"),
)


def _game_ready_marker():
    """返回当前画面命中的「游戏可操作」标志名；没有命中返回 None。"""
    for label, name in GAME_READY_MARKERS:
        try:
            if find_center_silent(get_template_path(name), 0.8, timeout=0):
                return label
        except (ValueError, OSError):
            # 个别模板缺失不应让整个就绪判定失败，跳过该标志即可
            continue
    return None


def wait_for_game_ready(timeout=GAME_READY_TIMEOUT, poll=GAME_READY_POLL):
    """等待游戏窗口出现、客户区尺寸稳定、且画面出现游戏内界面标志；返回 (status, message)。

    status 取值：
      "ok"        窗口在、尺寸在容差内、命中任一 GAME_READY_MARKERS；
      "no_window" 超时都没出现游戏窗口（快捷方式没起来 / 还停在启动器）；
      "not_ready" 窗口出现了，但超时时尺寸不符或画面始终没有游戏内标志。

    为什么不用「画面不黑」做判据：2026-11-12 冷启动实测，游戏自己的
    「正在更新游戏资源 21%」画面中心亮度足够高，`is_loading_screen()` 返回 False，
    于是亮度判据会把**加载中的画面**当成就绪，任务照样开跑、照样连败。
    只有模板标志（开始界面 / 主界面 HUD / 可交互弹窗）能真正区分「在加载」和「可操作」。
    """
    deadline = time.time() + max(1.0, timeout)
    seen_window = False
    last_note = ""
    while True:
        check_stop()
        hwnd = find_game_window()
        if hwnd is None:
            if time.time() >= deadline:
                return ("no_window",
                        f"等待 {int(timeout)} 秒仍未找到游戏窗口，游戏可能没有启动")
            time.sleep(poll)
            continue
        if not seen_window:
            seen_window = True
            log("已找到游戏窗口，等待画面就绪…")
        try:
            if ctypes.windll.user32.IsIconic(hwnd):
                ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE
                time.sleep(0.3)
        except (AttributeError, OSError):
            pass

        region = game_client_region()
        if region is None:
            last_note = "取不到客户区矩形"
        elif (abs(region[2] - CLIENT_WIDTH) > CLIENT_SIZE_TOLERANCE
              or abs(region[3] - CLIENT_HEIGHT) > CLIENT_SIZE_TOLERANCE):
            # 窗口还在启动动画/被拖拽缩放：尺寸不对就先不给结论
            last_note = (f"客户区尺寸 {region[2]}×{region[3]} 与模板基准 "
                         f"{CLIENT_WIDTH}×{CLIENT_HEIGHT} 不一致")
        else:
            marker = _game_ready_marker()
            if marker is not None:
                return ("ok", f"游戏已就绪（已出现{marker}，客户区 {region[2]}×{region[3]}）")
            last_note = "画面没有开始界面/主界面等标志（多半在资源校验或加载中）"

        if time.time() >= deadline:
            return "not_ready", f"等待 {int(timeout)} 秒后游戏仍未就绪：{last_note}"
        time.sleep(poll)


# ===== 无 OCR 区域变化检测（B2）=====
# 「某区域动作前后是否发生变化」在多个玩法里都要用：翻翻乐看钥匙余量、英雄厅堂看
# 等级数字、红点领取看页签行。比较与等待拆成两层，阈值与区域常量仍留在调用方
# （不同界面的噪声底不同，不能合并成一个全局数）。
def crops_differ(before_crop, after_crop, threshold):
    """判定两帧裁剪图是否「不再一致」；形状不一致视为未变化（与红点领取的既有语义一致）。

    用 TM_CCOEFF_NORMED 把 before 当作模板在 after 里自匹配：完全相同时为 1.0，
    界面真变化时明显掉分。阈值由调用方按各自界面的实测噪声底注入。
    """
    if before_crop.shape[:2] != after_crop.shape[:2]:
        return False
    return float(cv2.matchTemplate(after_crop, before_crop, cv2.TM_CCOEFF_NORMED).max()) < threshold


def region_changed_since(before_crop, region, *, threshold, timeout=3.0, interval=0.4):
    """轮询等待客户区某区域与 before_crop 不再一致；超时返回 False。

    region 是客户区相对坐标 (x, y, w, h)。每轮都重新取帧：0.4s 级轮询若用
    get_cached_screenshot 会一直拿到缓存旧帧，永远看不到变化。窗口取不到时按整屏
    原点裁剪（与 find_center 的全屏回退一致）。timeout=0 也会先确认一次，
    与仓库 `_wait_gone` 的既有语义一致。check_stop 放在循环内，F9 可随时中断。
    """
    deadline = time.time() + timeout
    while True:
        check_stop()
        frame = screenshot_bgr()
        rect = game_client_region()
        origin_x, origin_y = (rect[0], rect[1]) if rect else (0, 0)
        region_x, region_y, region_w, region_h = region
        left, top = origin_x + region_x, origin_y + region_y
        after_crop = frame[top:top + region_h, left:left + region_w]
        if crops_differ(before_crop, after_crop, threshold):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(interval)


# ===== HUD 固定点位入口（B6）=====
def _default_hud_click(client_pos):
    """HUD 入口的默认点击方式：客户区原点换算 + click_position 连点两下。

    窗口未在前台时第一次点击会被系统用于激活而吞掉（实测角落 HUD 图标单点无反应），
    因此默认连点两下。跳转型入口需要 twice=False 时，调用方注入自己的 click 回调。
    """
    region = game_client_region()
    origin_x, origin_y = (region[0], region[1]) if region else (0, 0)
    click_position((origin_x + client_pos[0], origin_y + client_pos[1]), twice=True)


def tap_hud_entry(client_pos, confirm, *, retries=2, click=None, log_func=None, precheck=False):
    """点固定 HUD 点位进入子面板：客户区原点换算 → 每轮尝试 → confirm 校验 → 失败日志。

    client_pos 是客户区相对坐标 (x, y)；换算成整屏坐标由 click 回调完成。各调用方
    把「本模块命名空间」的点击方式（wait / twice / send_coord 两次 + sleep）封装进
    闭包注入，既保留各自实测的点击节奏，也让测试对模块符号的 monkeypatch 继续生效。
    click 缺省为 _default_hud_click（客户区换算 + 连点两下）。
    precheck=True 时先调 confirm：已成立（例如已不在主界面）就直接返回 True，不点。
    confirm 每轮为假时累计重试 retries 轮，失败日志由 log_func(attempt) 输出。
    """
    if precheck and confirm():
        return True
    if click is None:
        click = _default_hud_click
    for attempt in range(1, retries + 1):
        check_stop()
        click(client_pos)
        if confirm():
            return True
        if log_func is not None:
            log_func(attempt)
        else:
            log(f"第 {attempt} 次点击 HUD 入口后未确认进入界面。")
    return False


def dismiss_popup_away_from(offset=(-400, -200), wait=1.5):
    """关闭「点击空白处关闭」类结算弹窗，但避开热区中心本身。

    「点击空白处关闭」文字固定在屏幕底部居中，而不少面板的主操作按钮（结社战线「扫荡」/
    狩猎悬赏「搜寻精怪」）正好压在它下方几个像素内：直接点模板中心，会在关掉弹窗的同时
    再触发一次那个按钮。故改点该文字左上方的空白处——同样在弹窗之外，能关闭且不会误触。
    与 common.dismiss_popup 的区别即在于此：后者点热区中心，适用于下方无按钮的界面。
    """
    pos = find_center_silent(get_template_path("dianjikongbaichuguanbi.png"), 0.8)
    if pos is None:
        return False
    return click_position((pos[0] + offset[0], pos[1] + offset[1]), wait)


# ===== 子脚本日志汇聚 =====
# 上层 GUI（Goldenhandmaidens）会调用 set_log_sink 把日志转发到应用内「运行日志」面板。
# 子脚本直接调用 log(...) 即可；未设置汇聚时回退为标准输出（便于单独调试子脚本）。
# 注意：log() 多在工作线程调用，直接操作 Tk 组件不安全。sink 回调应只把消息放入队列，
# 由主线程通过 after() 统一刷新面板（见 Goldenhandmaidens.update_log）。
_log_sink = None  # callable(str) 或 None


def set_log_sink(func):
    """设置日志汇聚回调，func 接收一条字符串消息；传 None 关闭汇聚。

    回调实现需是线程安全的（仅入队，不要直接操作 Tk 组件）。
    """
    global _log_sink
    _log_sink = func


def log(msg):
    """统一的调试日志输出：已设置汇聚回调则转发，否则回退到标准输出。
    注意：已设置汇聚时不再额外 print，避免上层 stdout 重定向造成重复。

    该函数在工作线程中被高频调用，sink 回调必须轻量且线程安全
    （仅把消息放入队列，由主线程 after() 刷新 UI）。
    """
    msg = str(msg)
    if _log_sink is not None:
        with contextlib.suppress(Exception):
            _log_sink(msg)
    else:
        print(msg)


def wait_and_click(template_path, name, threshold=0.8, timeout=None,
                   recover_threshold=0, recover_func=None, max_recoveries=2,
                   region=None, client_region=None):
    """
    等待模板出现并点击一次

    参数:
        template_path: 模板图片路径
        name: 操作名称（用于日志）
        threshold: 匹配阈值
        timeout: 超时时间（秒）
        recover_threshold: 连续检测失败达到该次数即触发一次兜底回主界面
            （默认 0 表示关闭）。用于任务卡在某界面时自动退出卡住处、再继续等待目标，
            避免一直卡在「检测不到 wanfamulu」等第一步导致整个任务停滞。
        recover_func: 自定义兜底恢复函数（默认使用 recover_to_main_interface）。
        max_recoveries: 单次调用内最多触发的兜底恢复次数（避免无限点击）。
        region: 整屏绝对坐标搜索范围 (x, y, w, h)，原样透传给 find_center。
        client_region: 客户区相对坐标搜索范围 (x, y, w, h)，透传给 find_center；
            与 region 互斥。位置未标定的界面不要指定。

    返回:
        True: 点击成功
        False: 超时未找到模板
    """
    start_time = time.time()
    attempt = 0
    miss_count = 0
    recover_count = 0

    # 如果没有指定超时时间，使用全局默认值
    wait_time = timeout if timeout is not None else MAX_WAIT

    while True:
        check_stop()
        attempt += 1
        pos = find_center(template_path, threshold=threshold,
                          region=region, client_region=client_region)
        if pos:
            print(f"{display_name(name)} 识别成功，第 {attempt} 次，坐标: {pos}，发送给 AHK 点击")
            send_coord(*pos)
            invalidate_screenshot_cache()
            return True

        miss_count += 1
        # 连续检测失败达到阈值：触发兜底回主界面，从卡住处退出后再继续等待目标，
        # 实现「反复检测不到 → 兜底退出 → 重新继续当前任务」的自动恢复。
        if recover_threshold and miss_count >= recover_threshold and recover_count < max_recoveries:
            miss_count = 0
            recover_count += 1
            log(f"{display_name(name)} 连续 {recover_threshold} 次未检测到，触发兜底回主界面（第 {recover_count} 次）")
            if recover_func is not None:
                recover_func()
            else:
                recover_to_main_interface()
            invalidate_screenshot_cache()

        elapsed = time.time() - start_time
        if elapsed > wait_time:
            print(f"{display_name(name)} 在 {wait_time} 秒内未出现，放弃等待。")
            return False

        print(f"{display_name(name)} 第 {attempt} 次未找到，{INTERVAL} 秒后重试（已等待 {elapsed:.1f} 秒）...")
        time.sleep(INTERVAL)


# ===== 阵容可采纳判定（push / flow_tower 共用，常量由调用方注入以避免行为分叉） =====
# 视为"低/高/未拥有"的数值，用于比较"仓库练度 >= 阵容要求练度"
LINEUP_DEFAULT_LEVEL_SCORE = {"未拥有": 0, "低": 1, "高": 2}
LINEUP_DEFAULT_SPECIAL_HERO_SET = set()


def is_lineup_acceptable(hero_levels, lineup_heroes, level_score=None, special_hero_set=None):
    """
    根据仓库练度 hero_levels 与当前阵容 lineup_heroes 判断是否可以采用：
    - 普通角色：自家练度 >= 阵容要求练度；
    - special_hero_set 中的角色：只要不是"未拥有"即可（高/低都行）。

    level_score / special_hero_set 由调用方注入，确保 push（SPECIAL_HERO_SET 含 meimo）
    与 flow_tower（不含）各自维持原有判定行为，避免共享常量导致分叉。两份原先各自维护的
    相同实现已收敛到此处，逻辑单源、行为完全不变。
    """
    if level_score is None:
        level_score = LINEUP_DEFAULT_LEVEL_SCORE
    if special_hero_set is None:
        special_hero_set = LINEUP_DEFAULT_SPECIAL_HERO_SET

    for hero_id, need_level in lineup_heroes:
        own_level = hero_levels.get(hero_id, "未拥有")

        # 特殊标注：只要拥有即可
        if hero_id in special_hero_set:
            if own_level == "未拥有":
                print(f"[阵容拒绝] 特殊角色 {hero_id} 未拥有。")
                return False
            print(f"[阵容通过] 特殊角色 {hero_id} 拥有（{own_level}），忽略需求 {need_level}。")
            continue

        own_score = level_score.get(own_level, 0)
        need_score = level_score.get(need_level, 1)  # 未能识别需求时，默认按"低"处理

        if own_score < need_score:
            print(
                f"[阵容拒绝] 角色 {hero_id} 自家练度={own_level}({own_score}) "
                f"< 需求练度={need_level}({need_score})"
            )
            return False

        print(
            f"[阵容通过] 角色 {hero_id} 自家练度={own_level}({own_score}) "
            f">= 需求练度={need_level}({need_score})"
        )

    return True


def click_template(template_path, label=None, threshold=0.8, timeout=None,
                   region=None, client_region=None):
    """通用"等待模板出现并点击"，薄封装 wait_and_click，供各 flow 脚本复用。

    flow_migong 的 click_mg 等按特定命名/阈值封装的点击均以此为基础，
    避免各脚本重复包装 wait_and_click。region / client_region 原样透传，
    语义见 wait_and_click。
    """
    if label is None:
        label = template_path
    return wait_and_click(template_path, label, threshold, timeout=timeout,
                          region=region, client_region=client_region)


def click_and_wait(click_name, next_name, timeout=10, cooldown=0.8,
                   click_finder=None, next_finder=None):
    """点击 A → 轮询检测 B → 冷却期后双检 A+B，A 仍在则重试。

    抽出自 flow_migong 的通用跳转辅助；仅依赖 send_coord 与 finder 回调，已与具体
    模板命名解耦。click_finder / next_finder 默认取 find_center（传路径），调用方通常
    传入自己的命名解析 finder（如 flow_migong 的 _find_root / find_mg）。

    timeout: 单次尝试超时（默认10s，覆盖慢加载空窗期）
    cooldown: 冷却期（0.8s，覆盖 A 残留/渐变消失）
    """
    if click_finder is None:
        click_finder = find_center
    if next_finder is None:
        next_finder = click_finder

    print(f"  {click_name} → {next_name}")

    for attempt in range(3):
        pos_a = click_finder(click_name)
        if pos_a is not None:
            send_coord(pos_a[0], pos_a[1])

        cooldown_start = time.time()
        overall_start = time.time()
        in_cooldown = True

        while time.time() - overall_start < timeout:
            pos_b = next_finder(next_name)
            if pos_b is not None:
                time.sleep(0.3)
                return True

            if in_cooldown:
                if time.time() - cooldown_start < cooldown:
                    time.sleep(0.12)
                    continue
                in_cooldown = False

            pos_a = click_finder(click_name, threshold=0.88)
            if pos_a is not None:
                print(f"    {click_name} 仍在，重试 ({attempt+1})")
                send_coord(pos_a[0], pos_a[1])
                cooldown_start = time.time()
                in_cooldown = True
                continue

            time.sleep(0.2)

        print(f"    {next_name} 超时 ({attempt+1}/3)")

    print(f"  ❌ {click_name} → {next_name} 失败")
    return False
