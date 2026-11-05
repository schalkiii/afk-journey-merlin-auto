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
import sys
import threading
import time
from collections import OrderedDict, deque
from ctypes import wintypes


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
        except Exception as exc:
            # 保留内置目录作为备用；不要让残缺的 APPDATA 目录被选中。
            try:
                if os.path.isdir(staging_dir):
                    shutil.rmtree(staging_dir)
            except OSError:
                pass
            print(f"APPDATA 模板缓存不可用，将回退内置模板目录: {exc}")
            _ACTIVE_TEMPLATES_DIR = bundled_dir
    except Exception as exc:
        print(f"APPDATA 模板缓存检查失败，将回退内置模板目录: {exc}")
        _ACTIVE_TEMPLATES_DIR = bundled_dir


def get_templates_dir():
    """模板目录：打包后优先 %APPDATA% 副本，其次内置目录；开发模式返回项目目录"""
    global _ACTIVE_TEMPLATES_DIR
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
    """获取工作目录下的文件路径（配置文件等）。

    打包后(sys.frozen)以 exe 所在目录为基准，保证配置文件与 exe 同目录、可持久化。
    """
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
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

# 底部导航带（客户区相对，按 1600×900）：主界面「玩法目录」入口与任务面板底部页签
# 都落在这条带内。保守取底部 250px，宁可面积大一点也不要漏判；实机截图后可再收窄。
BOTTOM_BAR_CLIENT_REGION = (0, 650, 1600, 250)


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
    except Exception as exc:
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
    """点击前确保游戏窗口在前台；否则先激活，避免第一次点击被系统吞掉。"""
    if not _auto_activate["enabled"]:
        return
    hwnd = find_game_window()
    if hwnd is None:
        return
    try:
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            time.sleep(0.2)
        if user32.GetForegroundWindow() == hwnd:
            return
        # 即使点击点属于游戏窗口，只要窗口不在前台，系统也可能把第一次点击用于激活而吞掉：
        # 先显式切前台，保证这次点击一定落到游戏上（实测幻灵入口偶发首次点击丢失）。
        _activate_game_window(hwnd)
        # 激活是异步的：不等一下就把坐标写过去，这一次点击仍可能被正在发生的窗口切换吃掉
        time.sleep(0.25)
        now = time.time()
        if now - _auto_activate["last_log"] > 5.0:
            _auto_activate["last_log"] = now
            log("游戏窗口不在前台，已自动切到前台后点击")
    except (AttributeError, OSError, ctypes.ArgumentError):
        pass


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

    与 find_center 的唯一区别是不输出相似度分数——适合在紧循环里高频调用，
    例如战斗监控、结算弹窗轮询，避免日志被分数刷屏。所有子脚本统一复用本实现，
    既消除各脚本重复定义，也保证 F9 停止检查（check_stop 内）一致生效。
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


def recover_to_main_interface(max_tries=8):
    """兜底回主界面：任务卡在某界面（弹窗 / 子界面）反复检测不到目标时使用。

    依次尝试点击「点击空白处关闭」(dianjikongbaichuguanbi)、tuichulibao（退出礼包）、
    exitck、exit（返回上一层），逐层从卡住处退出，直到 `at_main_interface()` 成立。
    无任何退出按钮时点击屏幕空白处兜底。供 wait_and_click 的兜底恢复与
    任务切换前的 ensure_main_interface 复用，避免把游戏停在中间界面导致后续任务卡死。
    """
    tpl_exit = get_template_path("exit.png")
    tpl_close = get_template_path("dianjikongbaichuguanbi.png")
    tpl_tuichulibao = get_template_path("tuichulibao.png")
    tpl_exitck = get_template_path("exitck.png")
    # 退出按钮尝试顺序：先关弹窗（空白关闭 / 退出礼包 / exitck），再返回上一层
    exit_templates = [tpl_close, tpl_tuichulibao, tpl_exitck, tpl_exit]

    for _ in range(max_tries):
        check_stop()
        if at_main_interface():
            return True
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


# 连续多少次坐标未被消费才判定点击器已退出：偶发的一次超时（窗口卡顿、系统繁忙）不算故障
CLICKER_MISS_LIMIT = 3
_clicker_miss = {"streak": 0}

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


def clicker_alive():
    """探测 click_from_file.exe 是否还在消费坐标文件。

    用「当前光标位置」作哨兵值而非固定坐标：点击器读到后会移动鼠标到该点，
    若用 (-1,-1) 之类的值会把光标甩到屏幕角落。
    """
    if os.path.exists(coord_path):
        return False   # 上一条坐标都没人取走，必然没在运行
    point = wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        return True    # 拿不到光标位置（非 Windows）：无法判断，按存活处理，不阻断流程
    with open(coord_path, "w", encoding="utf-8") as f:
        f.write(f"{point.x} {point.y}")
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if not os.path.exists(coord_path):
            return True
        time.sleep(0.05)
    return False


def send_coord(x, y):
    """将待点击坐标写入 IPC 文件，等待 AHK 消费完成后返回。

    先自旋等待上一条坐标被消费（文件消失），避免 AHK 尚未读取就被覆盖；
    写入后等待 AHK 读走本次坐标（文件被删除）再返回，替代原先无条件 0.5s 睡等——
    既更快（命中即返回），又更稳健（确保点击已发生）。期间 check_stop 允许 F9 中断。

    click_from_file.exe 会在长时间运行后自行退出，此后所有点击都会静默落空、界面表现为
    「连续多轮无变化」。因此连续 CLICKER_MISS_LIMIT 次坐标无人消费即抛 ClickerNotRunning，
    让调用方立即失败并报出真实原因，而不是空转到各流程自己的超时上限。
    """
    check_stop()
    ensure_game_clickable()
    cursor_before = _read_cursor_pos() if _restore_cursor["enabled"] else None
    wait_count = 0
    while os.path.exists(coord_path) and wait_count < 20:
        check_stop()  # 若 AHK 迟迟未消费上一条坐标，允许 F9 在此期间中断
        time.sleep(0.05)
        wait_count += 1

    with open(coord_path, "w", encoding="utf-8") as f:
        f.write(f"{x} {y}")

    # 等 AHK 读走本次坐标（文件被删除）再返回；最多 0.5s
    deadline = time.time() + 0.5
    while os.path.exists(coord_path):
        check_stop()
        if time.time() >= deadline:
            break
        time.sleep(0.02)

    if os.path.exists(coord_path):
        _clicker_miss["streak"] += 1
        if _clicker_miss["streak"] >= CLICKER_MISS_LIMIT:
            _clicker_miss["streak"] = 0
            log("点击注入未生效：click_from_file.exe 可能已退出，请重启程序或检查杀软拦截")
            raise ClickerNotRunning("click_from_file.exe 未在消费坐标")
    else:
        _clicker_miss["streak"] = 0

    if cursor_before is not None:
        # 等点击器把「移动 + 点击」做完再归位，否则可能被它随后的 MouseMove 覆盖
        time.sleep(0.12)
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
            print(f"{name} 识别成功，第 {attempt} 次，坐标: {pos}，发送给 AHK 点击")
            send_coord(*pos)
            invalidate_screenshot_cache()
            return True

        miss_count += 1
        # 连续检测失败达到阈值：触发兜底回主界面，从卡住处退出后再继续等待目标，
        # 实现「反复检测不到 → 兜底退出 → 重新继续当前任务」的自动恢复。
        if recover_threshold and miss_count >= recover_threshold and recover_count < max_recoveries:
            miss_count = 0
            recover_count += 1
            log(f"{name} 连续 {recover_threshold} 次未检测到，触发兜底回主界面（第 {recover_count} 次）")
            if recover_func is not None:
                recover_func()
            else:
                recover_to_main_interface()
            invalidate_screenshot_cache()

        elapsed = time.time() - start_time
        if elapsed > wait_time:
            print(f"{name} 在 {wait_time} 秒内未出现，放弃等待。")
            return False

        print(f"{name} 第 {attempt} 次未找到，{INTERVAL} 秒后重试（已等待 {elapsed:.1f} 秒）...")
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