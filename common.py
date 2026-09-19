# F:\afkj\game-bot\common.py
import cv2
import numpy as np
import pyautogui
import time
import os
import sys
import hashlib
import shutil

APP_DATA_ROOT = os.path.join(os.environ.get("APPDATA", ""), "gamebot")
APP_TEMPLATES_DIR = os.path.join(APP_DATA_ROOT, "templates")
_ACTIVE_TEMPLATES_DIR = None

def get_resource_path(relative_path):
    """获取资源文件的绝对路径，兼容打包后的exe"""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)

def _templates_marker(bundled_dir):
    """对模板目录内所有文件的相对路径+内容摘要做校验。"""
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
    _MEIPASS 临时目录导致模板文件丢失。启动时对比内容摘要，
    打包内容变化或副本缺失/损坏时重新复制；复制失败则回退使用内置目录。
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
        marker = _templates_marker(bundled_dir)
        if _is_valid_templates_dir(APP_TEMPLATES_DIR, marker):
            _ACTIVE_TEMPLATES_DIR = APP_TEMPLATES_DIR
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

def load_template(template_path):
    """读取模板；运行中发现缓存文件丢失时，修复缓存并重新定位一次。"""
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is not None:
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
            template = cv2.imread(repaired_path, cv2.IMREAD_COLOR)
            if template is not None:
                return template

    raise ValueError(f"模板读取失败: {template_path}")

ensure_appdata_templates()

def get_work_path(relative_path):
    """获取工作目录下的文件路径（配置文件等）"""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)

coord_path = get_work_path("shared\\target_coord.txt")
MAX_WAIT = 15
INTERVAL = 0.5

# 控制是否输出匹配得分信息
PRINT_MATCH_SCORE = True

def screenshot_bgr():
    shot = pyautogui.screenshot()
    return cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)

def find_center(template_path, threshold=0.8):
    template = load_template(template_path)
    h, w = template.shape[:2]

    img = screenshot_bgr()
    res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    
    if PRINT_MATCH_SCORE:
        print(f"{os.path.basename(template_path)} 匹配得分: {max_val:.3f}")

    if max_val < threshold:
        return None

    top_left = max_loc
    center_x = top_left[0] + w // 2
    center_y = top_left[1] + h // 2
    return center_x, center_y

def send_coord(x, y):
    wait_count = 0
    while os.path.exists(coord_path) and wait_count < 20:
        time.sleep(0.05)
        wait_count += 1
    
    with open(coord_path, "w", encoding="utf-8") as f:
        f.write(f"{x} {y}")
    time.sleep(0.5)

def wait_and_click(template_path, name, threshold=0.8, timeout=None, cooldown=None):
    """
    等待模板出现并点击一次
    
    参数:
        template_path: 模板图片路径
        name: 操作名称（用于日志）
        threshold: 匹配阈值
        timeout: 超时时间（秒）
        cooldown: 冷却时间（秒）
    
    返回:
        True: 点击成功
        False: 超时未找到模板
    """
    start_time = time.time()
    attempt = 0
    
    # 如果没有指定超时时间，使用全局默认值
    wait_time = timeout if timeout is not None else MAX_WAIT

    while True:
        attempt += 1
        pos = find_center(template_path, threshold=threshold)
        if pos:
            print(f"{name} 识别成功，第 {attempt} 次，坐标: {pos}，发送给 AHK 点击")
            send_coord(*pos)
            return True

        elapsed = time.time() - start_time
        if elapsed > wait_time:
            print(f"{name} 在 {wait_time} 秒内未出现，放弃等待。")
            return False

        print(f"{name} 第 {attempt} 次未找到，{INTERVAL} 秒后重试（已等待 {elapsed:.1f} 秒）...")
        time.sleep(INTERVAL)
