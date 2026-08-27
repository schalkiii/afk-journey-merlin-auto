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

import contextlib
import hashlib
import os
import shutil
import sys
import time

import cv2
import numpy as np
import pyautogui

APP_DATA_ROOT = os.path.join(os.environ.get("APPDATA", ""), "gamebot")
APP_TEMPLATES_DIR = os.path.join(APP_DATA_ROOT, "templates")

def get_resource_path(relative_path):
    """获取资源文件的绝对路径，兼容打包后的exe（sys._MEIPASS 指向解压目录）"""
    base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(__file__)
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


def screenshot_bgr():
    """截取屏幕并返回 BGR 格式 numpy 数组（OpenCV 标准色彩顺序）；短 TTL 内复用缓存帧。"""
    check_stop()
    now = time.time()
    if _screenshot_cache["img"] is not None and (now - _screenshot_cache["ts"]) < SCREENSHOT_CACHE_TTL:
        return _screenshot_cache["img"]
    screenshot = pyautogui.screenshot()
    img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    _screenshot_cache["img"] = img
    _screenshot_cache["ts"] = now
    return img


def get_cached_screenshot():
    """返回当前屏幕 BGR 数组（复用截图缓存，等价于 screenshot_bgr）。"""
    return screenshot_bgr()


def invalidate_screenshot_cache():
    """在点击导致界面变化后调用，使下一次截屏拿到最新帧而非缓存旧帧。"""
    _screenshot_cache["img"] = None
    _screenshot_cache["ts"] = 0.0


def find_center(template_path, threshold=0.8):
    """在截图中匹配模板，命中则返回其中心坐标 (x, y)，否则返回 None。

    使用 TM_CCOEFF_NORMED：对亮度/对比度变化不敏感，适合游戏 UI 这类
    整体色彩随场景浮动但局部纹理稳定的目标；默认阈值 0.8 在误触与漏触间取折中。
    """
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        raise ValueError(f"模板读取失败: {template_path}")
    template_h, template_w = template.shape[:2]

    screenshot = get_cached_screenshot()
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


def find_center_silent(template_path, threshold=0.8, region=None, timeout=0, interval=0.5):
    """find_center 的静默版本：命中返回中心坐标，否则返回 None，不打印匹配得分。

    与 find_center 的唯一区别是不输出相似度分数——适合在紧循环里高频调用，
    例如战斗监控、结算弹窗轮询，避免日志被分数刷屏。所有子脚本统一复用本实现，
    既消除各脚本重复定义，也保证 F9 停止检查（check_stop 内）一致生效。
    region: 限定搜索范围 (x, y, w, h) 以加快匹配；None 表示整屏。返回整屏绝对坐标。
    timeout: 持续轮询等待模板出现的秒数；0（默认）表示仅检测一次立即返回。
    interval: 轮询间隔（秒）。

    注：push.py 原先自带一份带 timeout 轮询的同名实现，现已统一委托本函数
    （push 内部以默认 timeout=3.0 的薄包装保留原语义），避免两份逻辑分叉。
    """
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        raise ValueError(f"模板读取失败: {template_path}")
    template_h, template_w = template.shape[:2]

    start_time = time.time()
    while True:
        check_stop()
        screenshot = get_cached_screenshot()
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
        if max_val >= threshold:
            # max_loc 为模板左上角坐标，加上半宽半高得到中心；region 裁剪需补偿偏移
            center_x = max_loc[0] + template_w // 2
            center_y = max_loc[1] + template_h // 2
            if region:
                center_x += region[0]
                center_y += region[1]
            return center_x, center_y

        if timeout <= 0:
            return None
        if time.time() - start_time >= timeout:
            return None
        time.sleep(interval)


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


def recover_to_main_interface(max_tries=8):
    """兜底回主界面：任务卡在某界面（弹窗 / 子界面）反复检测不到目标时使用。

    依次尝试点击「点击空白处关闭」(dianjikongbaichuguanbi)、tuichulibao（退出礼包）、
    exitck、exit（返回上一层），逐层从卡住处退出，直到主界面「玩法目录 wanfamulu」
    按钮可见。无任何退出按钮时点击屏幕空白处兜底。供 wait_and_click 的兜底恢复与
    任务切换前的 ensure_main_interface 复用，避免把游戏停在中间界面导致后续任务卡死。
    """
    tpl_wanfamulu = get_template_path("wanfamulu.png")
    tpl_exit = get_template_path("exit.png")
    tpl_close = get_template_path("dianjikongbaichuguanbi.png")
    tpl_tuichulibao = get_template_path("tuichulibao.png")
    tpl_exitck = get_template_path("exitck.png")
    # 退出按钮尝试顺序：先关弹窗（空白关闭 / 退出礼包 / exitck），再返回上一层
    exit_templates = [tpl_close, tpl_tuichulibao, tpl_exitck, tpl_exit]

    for _ in range(max_tries):
        check_stop()
        if find_center_silent(tpl_wanfamulu, 0.8):
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
    return find_center_silent(tpl_wanfamulu, 0.8) is not None


def ensure_main_interface():
    """任务切换前的兜底：先关闭残留弹窗，若仍未在主界面则逐层退出回到主界面。

    返回 True 表示已处于（或已回到）主界面。供运行循环在每个任务开始前调用，
    确保上一任务卡在子界面时，本次 wanfamulu 检测能正常进行，不连锁卡死后续任务。
    """
    dismiss_popup()
    tpl_wanfamulu = get_template_path("wanfamulu.png")
    if find_center_silent(tpl_wanfamulu, 0.8):
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

def send_coord(x, y):
    """将待点击坐标写入 IPC 文件，等待 AHK 消费完成后返回。

    先自旋等待上一个坐标被消费（文件消失），避免 AHK 尚未读取就被覆盖；
    写入后短暂延时，确保 AHK 有足够时间读到本次坐标。
    """
    check_stop()
    wait_count = 0
    while os.path.exists(coord_path) and wait_count < 20:
        check_stop()  # 若 AHK 迟迟未消费上一条坐标，允许 F9 在此期间中断
        time.sleep(0.05)
        wait_count += 1

    with open(coord_path, "w", encoding="utf-8") as f:
        f.write(f"{x} {y}")
    time.sleep(0.5)


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
                   recover_threshold=0, recover_func=None, max_recoveries=2):
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
        pos = find_center(template_path, threshold=threshold)
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


def click_template(template_path, label=None, threshold=0.8, timeout=None):
    """通用"等待模板出现并点击"，薄封装 wait_and_click，供各 flow 脚本复用。

    flow_migong 的 click_mg 等按特定命名/阈值封装的点击均以此为基础，
    避免各脚本重复包装 wait_and_click。
    """
    if label is None:
        label = template_path
    return wait_and_click(template_path, label, threshold, timeout=timeout)


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