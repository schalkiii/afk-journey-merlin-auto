# F:\afkj\game-bot\common.py
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
    """获取资源文件的绝对路径，兼容打包后的exe（sys._MEIPASS 指向解压目录）"""
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
    """获取工作目录下的文件路径（配置文件等）。

    打包后(sys.frozen)以 exe 所在目录为基准，保证配置文件与 exe 同目录、可持久化。
    """
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)

# 坐标 IPC 文件：send_coord 写入、click_from_file.exe(AHK) 读取后执行点击
coord_path = get_work_path("shared\\target_coord.txt")
# 单步匹配超时（秒）与轮询间隔（秒），供 wait_and_click 使用
MAX_WAIT = 15
INTERVAL = 0.5

# 调试开关：开启后打印每次匹配的相似度分数，便于校准模板阈值
PRINT_MATCH_SCORE = True


# ===== 协作式停止（F9 立即停止子脚本） =====
# 上层 GUI 调用 set_stop_checker(stop_event.is_set) 注入停止查询函数。
# 所有子脚本的「感知(screenshot_bgr)」与「动作(send_coord)」都会经过本模块，
# 在这两个底层原语处检查停止标志并抛出 StopRequested，即可穿透打断任何
# 正在运行的子脚本循环，无需逐个改造子脚本。
class StopRequested(BaseException):
    """用户请求停止（F9）。继承 BaseException，避免被子脚本中的
    except Exception 捕获吞掉，确保能一路冒泡到运行循环。"""
    pass


_stop_checker = None  # callable() -> bool 或 None


def set_stop_checker(func):
    """注入停止查询函数（返回 True 表示应停止）；传 None 关闭检查。"""
    global _stop_checker
    _stop_checker = func


def check_stop():
    """若已请求停止则抛出 StopRequested。子脚本长循环中也可主动调用。"""
    if _stop_checker is not None and _stop_checker():
        raise StopRequested("用户请求停止 (F9)")


def screenshot_bgr():
    """截取屏幕并返回 BGR 格式 numpy 数组（OpenCV 标准色彩顺序）"""
    check_stop()
    screenshot = pyautogui.screenshot()
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def find_center(template_path, threshold=0.8):
    """在截图中匹配模板，命中则返回其中心坐标 (x, y)，否则返回 None。

    使用 TM_CCOEFF_NORMED：对亮度/对比度变化不敏感，适合游戏 UI 这类
    整体色彩随场景浮动但局部纹理稳定的目标；默认阈值 0.8 在误触与漏触间取折中。
    """
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        raise ValueError(f"模板读取失败: {template_path}")
    template_h, template_w = template.shape[:2]

    screenshot = screenshot_bgr()
    # res 为与截图同尺寸的相关性矩阵，值越大表示越像模板
    match_result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(match_result)

    if PRINT_MATCH_SCORE:
        print(f"{os.path.basename(template_path)} 匹配得分: {max_val:.3f}")

    if max_val < threshold:
        return None

    # max_loc 为模板左上角坐标，加上半宽半高得到中心
    top_left = max_loc
    center_x = top_left[0] + template_w // 2
    center_y = top_left[1] + template_h // 2
    return center_x, center_y


def find_center_silent(template_path, threshold=0.8, region=None):
    """find_center 的静默版本：命中返回中心坐标，否则返回 None，不打印匹配得分。

    与 find_center 的唯一区别是不输出相似度分数——适合在紧循环里高频调用，
    例如战斗监控、结算弹窗轮询，避免日志被分数刷屏。所有子脚本统一复用本实现，
    既消除各脚本重复定义，也保证 F9 停止检查（screenshot_bgr 内）一致生效。
    region: 限定搜索范围 (x, y, w, h) 以加快匹配；None 表示整屏。返回整屏绝对坐标。
    """
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        raise ValueError(f"模板读取失败: {template_path}")
    template_h, template_w = template.shape[:2]

    screenshot = screenshot_bgr()
    if region:
        # 裁剪到图像有效范围：避免负坐标/越界导致 OpenCV 报错或误匹配
        x = max(0, region[0])
        y = max(0, region[1])
        roi_w = min(region[2], screenshot.shape[1] - x)
        roi_h = min(region[3], screenshot.shape[0] - y)
        if roi_w <= 0 or roi_h <= 0:
            return None
        search_area = screenshot[y:y + roi_h, x:x + roi_w]
        if search_area.shape[0] < template_h or search_area.shape[1] < template_w:
            return None
        match_result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
    else:
        match_result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)

    _, max_val, _, max_loc = cv2.minMaxLoc(match_result)
    if max_val < threshold:
        return None

    # max_loc 为模板左上角坐标，加上半宽半高得到中心；region 裁剪需补偿偏移
    center_x = max_loc[0] + template_w // 2
    center_y = max_loc[1] + template_h // 2
    if region:
        center_x += region[0]
        center_y += region[1]
    return center_x, center_y


def click_blank_to_exit():
    """点击屏幕空白区域以关闭弹窗/退出阵容视图的兜底手段。

    当「点击空白处关闭」(dianjikongbaichuguanbi) 模板检测不到时使用：
    游戏弹窗背后通常是可点击的半透明遮罩，点击远离弹窗中心的空白处即可关闭。
    这里点击屏幕底部居中（通常位于弹窗下方、远离按钮）的空白区域。
    """
    h, w = screenshot_bgr().shape[:2]
    # 底部居中：一般处于居中弹窗下方，是安全的可点击空白
    send_coord(w // 2, int(h * 0.85))
    time.sleep(0.5)


def dismiss_popup():
    """关闭游戏内弹窗（礼包广告 / 结算 / 战斗失败提示等）的兜底。

    优先点击「点击空白处关闭」(dianjikongbaichuguanbi) 模板；若检测不到，
    则点击屏幕空白处兜底。供任务切换（清理上一任务残留弹窗）与战斗任务
    失败清理复用，避免弹窗卡死后续流程。
    """
    tpl_blank_close = get_template_path("dianjikongbaichuguanbi.png")
    pos = find_center_silent(tpl_blank_close, 0.8)
    if pos:
        send_coord(*pos)
        time.sleep(0.5)
        return True
    # 模板检测不到时点击屏幕空白处兜底（兼容礼包广告等非标准弹窗）
    click_blank_to_exit()
    return True


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

    for attempt in range(retries):
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

def send_coord(x, y):
    """将待点击坐标写入 IPC 文件，等待 AHK 消费完成后返回。

    先自旋等待上一个坐标被消费（文件消失），避免 AHK 尚未读取就被覆盖；
    写入后短暂延时，确保 AHK 有足够时间读到本次坐标。
    """
    check_stop()
    wait_count = 0
    while os.path.exists(coord_path) and wait_count < 20:
        time.sleep(0.05)
        wait_count += 1

    with open(coord_path, "w", encoding="utf-8") as f:
        f.write(f"{x} {y}")
    time.sleep(0.5)


# ===== 子脚本日志汇聚 =====
# 上层 GUI（Goldenhandmaidens）会调用 set_log_sink 把日志转发到应用内「运行日志」面板。
# 子脚本直接调用 log(...) 即可；未设置汇聚时回退为标准输出（便于单独调试子脚本）。
_log_sink = None  # callable(str) 或 None


def set_log_sink(func):
    """设置日志汇聚回调，func 接收一条字符串消息；传 None 关闭汇聚。"""
    global _log_sink
    _log_sink = func


def log(msg):
    """统一的调试日志输出：已设置汇聚回调则转发，否则回退到标准输出。
    注意：已设置汇聚时不再额外 print，避免上层 stdout 重定向造成重复。"""
    msg = str(msg)
    if _log_sink is not None:
        try:
            _log_sink(msg)
        except Exception:
            pass
    else:
        print(msg)


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
        check_stop()
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