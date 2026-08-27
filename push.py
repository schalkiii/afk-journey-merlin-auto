import os
import time

import cv2

from common import find_center_silent as _common_find_center_silent
from common import (
    get_template_path,
    get_work_path,
    is_lineup_acceptable as _is_lineup_acceptable_impl,
    screenshot_bgr,
    wait_and_click,
)
from warehouse import (
    WAREHOUSE_TXT_PATH,
    init_templates_from_dir,
)


# 委托 common.find_center_silent：保留 push 内部「最多轮询等待 3s」的语义，
# 避免与 common 重复实现导致逻辑分叉（统一支持 region / 缓存截图 / F9 停止）。
def find_center_silent(template_path, threshold=0.7):
    return _common_find_center_silent(template_path, threshold=threshold, timeout=3.0)

# === 模板路径，对应你的文件名 ===
tpl_advance       = get_template_path("guajiguanqia.png")
tpl_wanfamulu     = get_template_path("wanfamulu.png")
tpl_huanlingcha   = get_template_path("tiaozhan.png")
tpl_autocha       = get_template_path("autocha.png")
tpl_fail          = get_template_path("fail.png")
tpl_repeat        = get_template_path("repeat.png")
tpl_lineup        = get_template_path("lineup.png")
tpl_artificial    = get_template_path("artificial.png")
tpl_right         = get_template_path("right.png")
tpl_oneclick      = get_template_path("oneclick.png")
tpl_exit          = get_template_path("exit.png")
tpl_end           = get_template_path("end.png")
tpl_not_owned     = get_template_path("not owned.png")
tpl_quxiao        = get_template_path("quxiao.png")

tpl_tiaozhanonly  = get_template_path("tiaozhanonly.png")

tpl_zidongtiaozhanzhong  = get_template_path("zidongtiaozhanzhong.png")

tpl_guajijixian   = get_template_path("guajijixian.png")
tpl_querengoumaimenpiao = get_template_path("querengoumaimenpiao.png")

tpl_huidaoguaji   = get_template_path("huidaoguaji.png")

# 推图模式配置：不同模式使用不同的入口模板
MODE_CONFIG = {
    "huanling": {
        "entry_templates": ["huanlingcha.png"],
    },
    "normal": {
        "entry_templates": ["tiaozhan.png", "tiaozhanonly.png"],
    },
}

# 一场战斗最长等待多久（秒）
MAX_BATTLE_TIME = 180

# ===== 阵容练度匹配相关配置 =====

# 视为"低/高/未拥有"的数值，用于比较"仓库练度 >= 阵容要求练度"
LEVEL_SCORE = {
    "未拥有": 0,
    "低": 1,
    "高": 2,
}

# 特殊标注角色：这些角色只要"拥有即可"（高/低都行），但不能是"未拥有"
# 直接填 warehouse_heroes.txt 里的名字（例如 "nvyao"）
SPECIAL_HERO_SET = {
    # 示例：在这里填你想放宽要求的角色
    # "nvyao",
    "meimo",
    "kululu",
    "shizi",
}

# 阵容界面 5 个头像的大致布局（相对于"一键采用"按钮）
# 你后续可以根据调试截图微调这些参数
LINEUP_CARD_WIDTH = 47
LINEUP_CARD_HEIGHT = 63
LINEUP_COL_GAP = 0

# 以一键采用按钮中心为参考点：
#   - X 起点 = btn_x - LINEUP_FIRST_OFFSET_X
#   - Y 起点 = btn_y - LINEUP_FIRST_OFFSET_Y
# （也就是头像区域大概在按钮上方一块区域）
LINEUP_FIRST_OFFSET_X = 200
LINEUP_FIRST_OFFSET_Y = 200

# 调试用整体偏移（像素）：正数表示向右/向下移动
# 参考：如果你想"向下 1 个框高"，就填 LINEUP_CARD_HEIGHT；"向右 1.3 个框宽"，就填 round(1.3 * LINEUP_CARD_WIDTH)
LINEUP_SHIFT_X_PX = round(1.6 * LINEUP_CARD_WIDTH)
LINEUP_SHIFT_Y_PX = round(0.75 * LINEUP_CARD_HEIGHT)

# 第二套布局：整体在 X 方向再额外平移的比例/像素
# 默认向左平移半个头像宽度，你可以调下面这两个变量：
LINEUP_SECOND_LAYOUT_SHIFT_X_FACTOR = -0.5
LINEUP_SECOND_LAYOUT_SHIFT_X_PX = round(LINEUP_SECOND_LAYOUT_SHIFT_X_FACTOR * LINEUP_CARD_WIDTH)

# 阵容界面头像明显比仓库里小，为了匹配稳定，
# 这里专门为阵容识别准备一套"更偏向缩小"的多尺度列表。
# 注意：这些只是模板缩放比例，不会改动截图本身。
LINEUP_TEMPLATE_SCALES = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

# 头像识别：多尺度模板匹配（解决不同分辨率/缩放导致头像大小不一致）
# - 你可以直接改这里的缩放范围与步进
LINEUP_HERO_TEMPLATE_SCALE_MIN = 0.40
LINEUP_HERO_TEMPLATE_SCALE_MAX = 0.80
LINEUP_HERO_TEMPLATE_SCALE_STEP = 0.05

# 英雄头像匹配阈值
LINEUP_HERO_MATCH_THRESHOLD = 0.6


# 调试截图输出目录
DEBUG_DIR = get_work_path("debug")

# Debug模式开关：True=开启调试功能（保存截图、打印调试信息），False=关闭调试功能
DEBUG_MODE = False

# 控制是否输出等待超时信息
PRINT_WAIT_TIMEOUT = False

# 阵容界面花边检测：只取头像框顶部多少比例作为检测条带
LINEUP_BORDER_TOP_RATIO = 0.08


def has_fancy_border_lineup(
    card_roi,
    top_ratio: float = LINEUP_BORDER_TOP_RATIO,
):
    """
    阵容界面专用的花边检测逻辑：
    - 只看卡片最上方 top_ratio（默认 10%）高度区域；
    - 对该条带做 Canny 边缘检测并统计边缘像素数；
    - 返回值 = 0: 没有花边；
    - 返回值 > 0: 有花边（边缘像素数）。

    返回 edge_count：
    - edge_count == 0: 没有花边
    - edge_count > 0: 有花边
    """
    if card_roi is None:
        return 0

    h, w = card_roi.shape[:2]
    if h <= 0 or w <= 0:
        return 0

    gray = cv2.cvtColor(card_roi, cv2.COLOR_BGR2GRAY)
    top_h = max(1, int(h * top_ratio))
    top_band = gray[0:top_h, :]

    edges = cv2.Canny(top_band, 50, 150)
    edge_count = int((edges > 0).sum())

    return edge_count


from warehouse import _match_best_hero  # 统一的多尺度英雄匹配循环


def _recognize_hero(card_roi):
    """
    识别卡片中的英雄 ID（阵容识别入口）。
    使用整卡区域匹配（与仓库扫描的上半 60% 裁切不同），并采用阵容专属的
    LINEUP_HERO_TEMPLATE_SCALE_* 尺度范围与 0.75 默认阈值（gubian/dashu/luka 0.8）。
    匹配循环统一委托 warehouse._match_best_hero，避免与仓库实现分叉。
    """
    if card_roi is None:
        return None

    h, w = card_roi.shape[:2]
    face_roi = card_roi[0:h, 0:w]

    best_hero, best_score = _match_best_hero(
        face_roi,
        LINEUP_HERO_TEMPLATE_SCALE_MIN,
        LINEUP_HERO_TEMPLATE_SCALE_MAX,
        LINEUP_HERO_TEMPLATE_SCALE_STEP,
    )

    # 不同英雄使用不同的匹配阈值
    if best_hero:
        if best_hero in ["gubian", "dashu", "luka"]:
            # gubian 和 dashu 要求准确率大于0.8
            if best_score > 0.8:
                print(f"识别到英雄 {best_hero}，相似度 {best_score:.3f}")
                return best_hero
        else:
            # 其他英雄使用0.75的阈值
            if best_score >= 0.75:
                print(f"识别到英雄 {best_hero}，相似度 {best_score:.3f}")
                return best_hero

    return None


def wait_for_appearance(template_path, name, threshold=0.8, timeout=MAX_BATTLE_TIME, interval=0.5):
    """循环等待某张图出现，出现返回坐标，超时返回 None。"""
    start = time.time()
    attempt = 0
    while True:
        attempt += 1
        pos = find_center_silent(template_path, threshold)
        if pos:
            if PRINT_WAIT_TIMEOUT:
                print(f"{name} 出现，第 {attempt} 次检测，坐标: {pos}")
            return pos

        elapsed = time.time() - start
        if elapsed > timeout:
            if PRINT_WAIT_TIMEOUT:
                print(f"{name} 在 {timeout} 秒内未出现，放弃等待。")
            return None

        if PRINT_WAIT_TIMEOUT:
            print(f"{name} 第 {attempt} 次未出现，{interval} 秒后重试（已等待 {elapsed:.1f} 秒）...")
        time.sleep(interval)


def wait_for_any(templates, threshold=0.8, timeout=MAX_BATTLE_TIME, interval=0.5):
    """
    循环等待多张图中的任意一张出现。

    templates: List[Tuple[template_path, name]]
    返回：
        - (template_path, name, pos) 命中
        - None 超时
    """
    start = time.time()
    attempt = 0
    while True:
        attempt += 1
        for template_path, name in templates:
            pos = find_center_silent(template_path, threshold)
            if pos:
                if PRINT_WAIT_TIMEOUT:
                    print(f"{name} 出现，第 {attempt} 次检测，坐标: {pos}")
                return template_path, name, pos

        elapsed = time.time() - start
        if elapsed > timeout:
            if PRINT_WAIT_TIMEOUT:
                names = " / ".join([n for _, n in templates])
                print(f"{names} 在 {timeout} 秒内未出现，放弃等待。")
            return None

        time.sleep(interval)


def _load_warehouse_levels():
    """
    读取仓库扫描结果文本，生成 {hero_name: level_str} 字典。
    文本每行格式为：名字,高/低/未拥有
    """
    hero_levels = {}
    if not os.path.exists(WAREHOUSE_TXT_PATH):
        print(f"未找到仓库练度文件：{WAREHOUSE_TXT_PATH}，将视为全部未拥有。")
        return hero_levels

    with open(WAREHOUSE_TXT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "," not in line:
                continue
            name, lvl = line.split(",", 1)
            hero_levels[name.strip()] = lvl.strip()
    print(f"已读取仓库练度信息，共 {len(hero_levels)} 条。")
    return hero_levels


def _capture_lineup_slots(debug_label="lineup", extra_shift_x_px: int = 0):
    """
    在"通关阵容界面"下：
    - 通过 oneclick(i) 按钮位置估算 5 个头像的大致区域；
    - 返回 [(card_roi, (x, y, w, h)), ...]；
    - 如果 DEBUG_MODE 为 True，同时输出一张画有绿框的调试大图到 DEBUG_DIR。
    """
    img = screenshot_bgr()
    pos_btn = find_center_silent(tpl_oneclick, threshold=0.8)
    if not pos_btn:
        print("未找到一键采用按钮，无法估算阵容 5 个头像位置。")
        return []

    btn_x, btn_y = pos_btn
    ih, iw = img.shape[:2]

    # 估算第一张头像左上角
    x0 = max(
        0,
        round(
                (btn_x - LINEUP_FIRST_OFFSET_X) + LINEUP_SHIFT_X_PX
            ),
    ) + extra_shift_x_px
    y0 = max(
        0,
        round(
                (btn_y - LINEUP_FIRST_OFFSET_Y) + LINEUP_SHIFT_Y_PX
            ),
    )

    slots = []
    vis = img.copy()

    for idx in range(5):
        x = x0 + idx * (LINEUP_CARD_WIDTH + LINEUP_COL_GAP)
        y = y0
        w = LINEUP_CARD_WIDTH
        h = LINEUP_CARD_HEIGHT

        if x < 0 or y < 0 or x + w > iw or y + h > ih:
            continue

        roi = img[y : y + h, x : x + w]
        slots.append((roi, (x, y, w, h)))
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)

    if DEBUG_MODE:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        debug_path = os.path.join(
            DEBUG_DIR,
            f"{debug_label}_{int(time.time())}.png",
        )
        cv2.imwrite(debug_path, vis)
        print(f"阵容头像调试截图已保存：{debug_path}")

    return slots


def _recognize_lineup_with_levels():
    """
    识别当前通关阵容界面的 5 个角色及其"高/低/未拥有"：
    - 使用仓库里的头像识别逻辑 _recognize_hero；
    - 使用 has_fancy_border 判断是否有花边：有花边=高，无花边=低，空槽=未拥有。
    返回：
        lineup_heroes: List[(hero_name, need_level_str)]
        debug_path: 调试截图路径（可能为 None）
    """
    init_templates_from_dir()

    # 两套布局：第一套为默认位置，第二套整体再往左平移一段距离
    layouts = [
        ("layout1", 0),
        ("layout2", LINEUP_SECOND_LAYOUT_SHIFT_X_PX),
    ]

    best_lineup = []
    best_debug_path = None
    best_count = -1

    for layout_name, extra_shift in layouts:
        slots = _capture_lineup_slots(
            debug_label=f"lineup_debug_{layout_name}",
            extra_shift_x_px=extra_shift,
        )
        if not slots:
            continue

        lineup_heroes = []

        # 重新生成一张可视化图，包含识别结果文字
        img = screenshot_bgr()
        vis = img.copy()

        for _idx, (roi, (x, y, w, h)) in enumerate(slots):
            edge_cnt = has_fancy_border_lineup(roi)
            need_level = "高" if edge_cnt > 0 else "低"

            # 阵容头像比仓库小一圈，使用仓库中定义的多尺度匹配逻辑
            hero_id = _recognize_hero(roi)
            if hero_id:
                lineup_heroes.append((hero_id, need_level))
                label = f"{hero_id}:{need_level}"
            else:
                label = f"未知:{need_level}"

            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(
                vis,
                label,
                (x, max(0, y - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

        recognized_count = len([h for h, lvl in lineup_heroes if h])

        debug_path = None
        if DEBUG_MODE:
            debug_path = os.path.join(
                DEBUG_DIR,
                f"lineup_recognized_{layout_name}_{int(time.time())}.png",
            )
            cv2.imwrite(debug_path, vis)
            print(f"[{layout_name}] 阵容识别结果截图已保存：{debug_path}")

        print(f"[{layout_name}] 当前阵容识别结果：")
        for hero_id, need_level in lineup_heroes:
            print(f"  - {hero_id}，需要练度：{need_level}")

        # 选择规则：
        # 1. 优先选择"识别到 5 个角色"的布局；
        # 2. 如果两套都不是 5 个，则保留识别数量更多的那套；
        # 3. 数量相同则保留先出现的（保持原有行为为主）。
        if recognized_count == 5:
            best_lineup = lineup_heroes
            best_debug_path = debug_path
            best_count = recognized_count
            # 已经满足"5 个角色全识别"，可以直接结束循环
            break

        if recognized_count > best_count:
            best_lineup = lineup_heroes
            best_debug_path = debug_path
            best_count = recognized_count

    return best_lineup, best_debug_path


def _is_lineup_acceptable(hero_levels, lineup_heroes):
    """阵容可采纳判定（判定逻辑见 common.is_lineup_acceptable，注入本模块练度常量以维持原有行为）。"""
    return _is_lineup_acceptable_impl(hero_levels, lineup_heroes, LEVEL_SCORE, SPECIAL_HERO_SET)


def debug_lineup_recognition():
    """
    调试函数（仅阵容识别，不参与推图流程）：
    - 请手动停留在"查看通关阵容界面"；
    - 直接运行本脚本，将：
        * 估算 5 个阵容头像框的位置并画绿框截一张调试大图；
        * 对每个槽位调用 has_fancy_border + _recognize_hero；
        * 在控制台打印「槽位索引 / 英雄 ID / 花边状态 / 边缘像素数」。
    """
    init_templates_from_dir()

    layouts = [
        ("layout1", 0),
        ("layout2", LINEUP_SECOND_LAYOUT_SHIFT_X_PX),
    ]

    for layout_name, extra_shift in layouts:
        slots = _capture_lineup_slots(
            debug_label=f"lineup_debug_{layout_name}",
            extra_shift_x_px=extra_shift,
        )
        if not slots:
            print(f"[{layout_name}] 未能获取到阵容头像槽位，确认是否已经在阵容界面。")
            continue

        print(f"--------- {layout_name} 阵容头像调试结果（索引 / 英雄ID / 花边状态 / 边缘像素数）---------")
        for idx, (roi, (_x, _y, _w, _h)) in enumerate(slots):
            edge_cnt = has_fancy_border_lineup(roi)
            border_str = "有花边" if edge_cnt > 0 else "无花边"

            # 使用仓库中定义的多尺度匹配逻辑
            hero_id = _recognize_hero(roi)
            hero_str = hero_id if hero_id else "未识别"
            print(f"[{idx}] 英雄={hero_str}，边框={border_str}，边缘像素数={edge_cnt}")

    print("如需查看框位置，请打开 debug 目录中的 lineup_debug_layout*_*.png 截图。")


def select_lineup(start_index: int, skip_manual: bool = True):
    """
    在"通关阵容界面"里，从编号 start_index 开始往后找可用阵容。

    skip_manual=True: 跳过含手动战斗标志 artificial(g) 的阵容
    skip_manual=False: 不检测手动标志，仅判断练度
    """
    # 1. 先把光标移到 start_index 对应的阵容（跳过之前用过的）
    current_index = 0
    if start_index > 0:
        print(f"进入阵容界面，先向右点击 {start_index} 次，跳过已经用过的阵容。")
    else:
        print("进入阵容界面，先向右点击 0 次，跳过已经用过的阵容。")

    while current_index < start_index:
        if not wait_and_click(tpl_right, f"right(h) 跳过阵容 {current_index}", 0.8):
            # 还没跳够 start_index 次就已经点不到 right 了，说明本来阵容数就没那么多
            print("阵容数量不足以跳到指定起点，采用当前可见阵容并视为无更多阵容。")
            if not wait_and_click(tpl_oneclick, "oneclick(i_at_end)", 0.8):
                return None
            return None
        current_index += 1
        time.sleep(0.5)

    # 2. 从 current_index（>= start_index）开始往后找可用阵容
    while True:
        if skip_manual:
            print(f"检查阵容编号 {current_index} 是否含有手动战斗标志 g。")
            pos_g = find_center_silent(tpl_artificial, threshold=0.8)
        else:
            pos_g = None

        if not pos_g:
            # 没有 g，继续做练度匹配判断
            hero_levels = _load_warehouse_levels()
            lineup_heroes, _debug_path = _recognize_lineup_with_levels()
            if _is_lineup_acceptable(hero_levels, lineup_heroes):
                if not wait_and_click(tpl_oneclick, f"oneclick(i) 采用阵容 {current_index}", 0.8):
                    return None
                
                # 点击一键采用后，等待一段时间检测是否出现 not owned.png
                time.sleep(1.0)
                pos_not_owned = find_center_silent(tpl_not_owned, threshold=0.8)
                
                if pos_not_owned:
                    # 检测到 not owned.png，说明该阵容不可用，点击取消并继续检查下一个阵容
                    print(f"阵容 {current_index} 检测到未拥有标志，点击取消并跳过。")
                    if not wait_and_click(tpl_quxiao, "quxiao(m) 取消当前阵容", 0.8):
                        print("点击取消失败，跳过当前阵容。")
                    # 等待返回阵容选择界面
                    time.sleep(1.0)
                    # 继续检查下一个阵容
                    print(f"阵容 {current_index} 不可用，尝试切到下一套。")
                    if not wait_and_click(tpl_right, f"right(h) 从阵容 {current_index} 切到下一套", 0.8):
                        # 点不到 right 说明已经是最后一套
                        print("已经是最后一套阵容，且检测到未拥有标志，仍然采用当前阵容后返回 None。")
                        if not wait_and_click(tpl_oneclick, "oneclick(i_last)", 0.8):
                            return None
                        return None
                    current_index += 1
                    time.sleep(0.5)
                    continue  # 继续检查下一个阵容
                
                # 没有检测到 not owned.png，正常采用该阵容
                print(f"采用当前阵容，编号为 {current_index}。")
                return current_index

            print(f"阵容 {current_index} 练度不足，尝试切到下一套。")
            # 练度不满足，视作"不可用"，继续下面像含 g 一样处理

        # 有 g：尝试切到下一套阵容
        print(f"阵容 {current_index} 含 g 或练度不满足，尝试点击 right(h) 切到下一套。")
        if not wait_and_click(tpl_right, f"right(h) 从阵容 {current_index} 切到下一套", 0.8):
            # 点不到 right 说明已经是最后一套
            print("已经是最后一套阵容，且含 g，仍然采用当前阵容后返回 None。")
            if not wait_and_click(tpl_oneclick, "oneclick(i_last)", 0.8):
                return None
            return None

        current_index += 1
        time.sleep(0.5)


def _try_detect_and_click_entry(entry_templates, timeout=3):
    """检测入口模板列表中的任意一个，检测到后点击。返回 True 表示成功。"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        for tpl_name in entry_templates:
            tpl_path = get_template_path(tpl_name)
            if find_center_silent(tpl_path, threshold=0.8):
                print(f"检测到 {tpl_name}，点击进入")
                if not wait_and_click(tpl_path, tpl_name, 0.8):
                    print(f"点击 {tpl_name} 失败")
                    return False
                return True
        time.sleep(0.5)
    return False


def flow_push_mode1(mode="normal", skip_manual=True, retry_count=3):
    """
    推图主流程。

    mode: "normal"（普通推图）或 "huanling"（幻灵推图）
    skip_manual: 是否跳过含手动战斗标志的阵容
    retry_count: 同一阵容连续失败多少次后换阵容（1-3）
    """
    entry_templates = MODE_CONFIG[mode]["entry_templates"]
    mode_label = "幻灵推图" if mode == "huanling" else "推图"

    init_templates_from_dir()

    # 1. 点击 wanfamulu 进入玩法目录
    if not wait_and_click(tpl_wanfamulu, "wanfamulu", 0.7, recover_threshold=20):
        print("点击 wanfamulu 进入玩法目录失败。")
        return False

    # 2. 点击 advance(a) 进入推图玩法
    if not wait_and_click(tpl_advance, "advance(a)", 0.8):
        print("点击 advance(a) 进入推图失败。")
        return False

    # 3. 检测入口模板
    print(f"等待 3 秒检查是否出现 {mode_label} 入口...")
    if not _try_detect_and_click_entry(entry_templates, timeout=3):
        names = " / ".join(entry_templates)
        print(f"3 秒内未检测到 {names}，点击 exit 退出")
        wait_and_click(tpl_exit, "exit(j)", 0.8)
        return False

    print(f"进入 {mode_label} 成功")

    # 4. 检查是否出现 guajijixian
    print("等待 3 秒检查是否出现 guajijixian...")
    start_time = time.time()
    guajijixian_found = False
    
    while time.time() - start_time < 3:
        if find_center_silent(tpl_guajijixian, threshold=0.7):
            print("检测到 guajijixian，点击 querengoumaimenpiao...")
            if wait_and_click(tpl_querengoumaimenpiao, "querengoumaimenpiao", 0.7):
                print("点击 querengoumaimenpiao 成功")
                guajijixian_found = True
            break
        time.sleep(0.5)
    
    if guajijixian_found:
        print("检测到 guajijixian，点击 querengoumaimenpiao 后点击 autocha")
    else:
        print("3 秒内未检测到 guajijixian，直接点击 autocha")

    have_custom_lineup = False     # 是否已经从阵容界面选过阵容
    current_lineup_index = -1      # 当前阵容编号（初始为 -1，表示还没选过）
    current_lineup_fail = 0        # 当前阵容连续失败次数
    need_reenter_mode1 = False     # 图 k 后会回到玩法界面，需要重新点 b 进入模式1

    while True:
        if need_reenter_mode1:
            if not _try_detect_and_click_entry(entry_templates, timeout=5):
                names = " / ".join(entry_templates)
                print(f"5 秒内未检测到 {names}，退出推图")
                return False
            need_reenter_mode1 = False

        # 3. 在推图界面点击 autocha(c) 自动挑战
        if not wait_and_click(tpl_autocha, "autocha(c)", 0.8):
            print("未找到 autocha(c)，推图流程结束。")
            return False

        # 4. 等待失败：
        # - fail(d)：当前关卡直接失败（需要累计失败次数防止一直用同一阵容）
        # - end(k)：通过若干关卡后失败（需要重置失败计数，且点击后会回到推图玩法界面）
        # 同时监控自动挑战中标志 zidongtiaozhanzhong：只要定期看到它，就认为还在正常推图中，不做"无法判断"处理。
        hit = None
        # 只根据"距最近一次看到自动挑战中标志"的时间来判断是否超时：
        # - 一旦识别到 zidongtiaozhanzhong.png，就重置 last_seen_zidong；
        # - 如果连续超过 3 分钟都没再识别到它，且期间也没有失败标志，则认为无法判断当前状态。
        last_seen_zidong = time.time()

        while True:
            hit = wait_for_any(
                [(tpl_fail, "fail(d)"), (tpl_end, "end(k)")],
                threshold=0.8,
                timeout=1.0,  # 更小的步长轮询，以便更及时地检测 zidongtiaozhanzhong
                interval=0.5,
            )
            if hit:
                break

            # 每轮失败检查之间，顺便看一下是否还能看到自动挑战中标志
            pos_zidong = find_center_silent(tpl_zidongtiaozhanzhong, threshold=0.8)
            if pos_zidong:
                last_seen_zidong = time.time()

            now = time.time()
            # 检查是否超过 5 秒未检测到 zidongtiaozhanzhong，可能是误触导致弹窗
            if (now - last_seen_zidong) > 5:
                print("超过 5 秒未检测到 zidongtiaozhanzhong，可能出现误触弹窗，尝试识别 huidaoguaji...")
                # 只等待 1 秒识别 huidaoguaji，因为 5 秒未检测到 zidongtiaozhanzhong 本身就是在给 huidaoguaji 留加载时间
                if wait_and_click(tpl_huidaoguaji, "huidaoguaji", 0.8, timeout=1.0):
                    print("点击 huidaoguaji 成功，重新开始 3 分钟计时...")
                    last_seen_zidong = time.time()  # 重新开始 3 分钟计时

            # 如果 3 分钟（180 秒）内一直没看到 zidongtiaozhanzhong，
            # 且也没检测到失败标志，才认为"无法判断当前状态"，结束本次流程。
            if (now - last_seen_zidong) > 180:
                print(
                    "超过 3 分钟未检测到自动挑战中标志 zidongtiaozhanzhong.png，"
                    "且未检测到失败标志 fail(d)/end(k)，无法判断当前状态，结束本次推图流程。"
                )
                return True

        hit_tpl, hit_name, _ = hit
        if hit_tpl == tpl_end:
            # 图 k：通过一段关卡后失败，不应计入"同一关连续失败"
            current_lineup_fail = 0
            current_lineup_index = -1  # 重置阵容编号
            have_custom_lineup = False  # 标记为未选择阵容
            print("检测到 end(k)：重置当前阵容连续失败次数、阵容编号，并重新进入模式1。")
            if not wait_and_click(tpl_end, "end(k)_click", 0.8):
                print("点击 end(k) 失败，退出推图。")
                return False
            need_reenter_mode1 = True
            continue

        # 5. 检测到失败图 d 后，点击 repeat(e) 回到推图界面
        if not wait_and_click(tpl_repeat, "repeat(e)", 0.8):
            print("点击 repeat(e) 失败，退出推图。")
            return False

        # 6. 阵容调整逻辑
        if not have_custom_lineup:
            # 第一次失败：先进入阵容界面，从 0 开始选一套"无 g 的阵容"
            if not wait_and_click(tpl_lineup, "lineup(f_first)", 0.8):
                print("点击 lineup(f) 进入通关阵容界面失败。")
                return False

            idx = select_lineup(start_index=0, skip_manual=skip_manual)
            if idx is None:
                # 阵容用尽或异常，退出推图
                wait_and_click(tpl_exit, "exit(j)", 0.8)
                time.sleep(1.0)
                wait_and_click(tpl_exit, "exit(j)", 0.8)
                return False

            have_custom_lineup = True
            current_lineup_index = idx
            current_lineup_fail = 0
            print(f"首次选定阵容编号 {current_lineup_index}，接下来用该阵容推图。")
            continue  # 回到 while 顶部，再次 autocha
        else:
            # 已经有阵容在用：累加失败次数
            current_lineup_fail += 1
            print(f"当前阵容 {current_lineup_index} 连续失败次数: {current_lineup_fail}")

            if current_lineup_fail < retry_count:
                # 还没到重试上限，继续用当前阵容
                continue

            # 同一阵容失败达到上限：再进入阵容界面，从下一套开始找
            if not wait_and_click(tpl_lineup, "lineup(f_again)", 0.8):
                print("再次点击 lineup(f) 进入通关阵容界面失败。")
                return False

            next_start = current_lineup_index + 1
            idx = select_lineup(start_index=next_start, skip_manual=skip_manual)
            if idx is None:
                # 已经没有新的阵容可选：采用后退出推图到最外层
                print("没有更多可选阵容，退出推图。")
                wait_and_click(tpl_exit, "exit(j)", 0.8)
                time.sleep(1.0)
                wait_and_click(tpl_exit, "exit(j)", 0.8)
                return False

            current_lineup_index = idx
            current_lineup_fail = 0
            print(f"切换到新阵容编号 {current_lineup_index}，失败计数清零。")
            continue  # 回到 while 顶部，用新阵容继续 autocha


def main(skip_manual=True, retry_count=3):
    """主函数，供其他脚本调用"""
    if DEBUG_MODE:
        debug_lineup_recognition()
    else:
        flow_push_mode1(mode="normal", skip_manual=skip_manual, retry_count=retry_count)

if __name__ == "__main__":
    main()