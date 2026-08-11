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

def get_resource_path(relative_path):
    """获取资源文件的绝对路径，兼容打包后的exe"""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)

def _templates_marker(bundled_dir):
    """对模板目录内所有文件的相对路径+大小做摘要，用于判断打包内容是否有变化"""
    entries = []
    for root, _, files in os.walk(bundled_dir):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, bundled_dir)
            try:
                size = os.path.getsize(fpath)
            except OSError:
                continue
            entries.append(f"{rel}:{size}")
    return hashlib.md5("\n".join(entries).encode("utf-8", "surrogatepass")).hexdigest()

def ensure_appdata_templates():
    """
    打包后把内置模板复制到 %APPDATA%\\gamebot\\templates，避免杀软清理
    _MEIPASS 临时目录导致模板文件丢失。启动时对比内容摘要，
    打包内容变化或副本缺失/损坏时重新复制；复制失败则回退使用内置目录。
    """
    if not getattr(sys, "frozen", False) or not APP_DATA_ROOT:
        return
    bundled_dir = get_resource_path("templates")
    if not os.path.isdir(bundled_dir):
        return
    try:
        marker = _templates_marker(bundled_dir)
        if os.path.isdir(APP_TEMPLATES_DIR):
            if _templates_marker(APP_TEMPLATES_DIR) == marker:
                return
            shutil.rmtree(APP_TEMPLATES_DIR)
        shutil.copytree(bundled_dir, APP_TEMPLATES_DIR)
    except Exception:
        pass

def get_templates_dir():
    """模板目录：打包后优先 %APPDATA% 副本，其次内置目录；开发模式返回项目目录"""
    if getattr(sys, "frozen", False) and os.path.isdir(APP_TEMPLATES_DIR):
        return APP_TEMPLATES_DIR
    return get_resource_path("templates")

def get_template_path(template_name, subdir=None):
    """获取模板图片路径，可指定子目录"""
    if subdir:
        return os.path.join(get_templates_dir(), subdir, template_name)
    return os.path.join(get_templates_dir(), template_name)

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
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        raise ValueError(f"模板读取失败: {template_path}")
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