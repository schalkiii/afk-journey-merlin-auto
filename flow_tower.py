"""爬塔流程模块：自动挑战并识别阵容、提交战斗。

依赖 warehouse 的英雄模板与 common 的匹配/点击能力；战斗前后会读取仓库英雄，
按配置上阵并识别胜利/失败以决定继续或停止。
"""

import os
import random
import time

import cv2

from common import (
    find_center,
    find_center_silent,
    get_template_path,
    get_work_path,
    is_lineup_acceptable as _is_lineup_acceptable_impl,
    screenshot_bgr,
    send_coord,
    wait_and_click,
)
from warehouse import (
    WAREHOUSE_TXT_PATH,
    init_templates_from_dir,
)


# 随机等待函数，2-3秒
def random_sleep():
    time.sleep(random.uniform(2.0, 3.0))

# 检测手动战斗标志，返回得分和坐标
def check_artificial_score(threshold=0.7):
    template = cv2.imread(tpl_artificial, cv2.IMREAD_COLOR)
    if template is None:
        raise ValueError(f"模板读取失败: {tpl_artificial}")
    h, w = template.shape[:2]

    img = screenshot_bgr()
    res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val >= threshold:
        top_left = max_loc
        center_x = top_left[0] + w // 2
        center_y = top_left[1] + h // 2
        return max_val, (center_x, center_y)
    return max_val, None

# === 模板路径，对应你的文件名 ===
tpl_wanfamulu     = get_template_path("wanfamulu.png")
tpl_pata          = get_template_path("pata.png")
tpl_ziranzhita    = get_template_path("ziranzhita.png")
tpl_patatiaozhan  = get_template_path("patatiaozhan.png")
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
tpl_dianjikongbaichuguanbi = get_template_path("dianjikongbaichuguanbi.png")

tpl_zidongtiaozhanzhong  = get_template_path("zidongtiaozhanzhong.png")

# 一场战斗最长等待多久（秒）
MAX_BATTLE_TIME = 180

# ===== 阵容练度匹配相关配置 =====

# 视为“低/高/未拥有”的数值，用于比较“仓库练度 >= 阵容要求练度”
LEVEL_SCORE = {
    "未拥有": 0,
    "低": 1,
    "高": 2,
}

# 特殊标注角色：这些角色只要“拥有即可”（高/低都行），但不能是“未拥有”
# 直接填 warehouse_heroes.txt 里的名字（例如 "nvyao"）
SPECIAL_HERO_SET = {
    # 示例：在这里填你想放宽要求的角色
    # "nvyao",
}

# 阵容界面 5 个头像的大致布局（相对于“一键采用”按钮）
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
# 参考：如果你想“向下 1 个框高”，就填 LINEUP_CARD_HEIGHT；“向右 1.3 个框宽”，就填 round(1.3 * LINEUP_CARD_WIDTH)
LINEUP_SHIFT_X_PX = round(1.6 * LINEUP_CARD_WIDTH)
LINEUP_SHIFT_Y_PX = round(0.75 * LINEUP_CARD_HEIGHT)

# 第二套布局：整体在 X 方向再额外平移的比例/像素
# 默认向左平移半个头像宽度，你可以调下面这两个变量：
LINEUP_SECOND_LAYOUT_SHIFT_X_FACTOR = -0.5
LINEUP_SECOND_LAYOUT_SHIFT_X_PX = round(LINEUP_SECOND_LAYOUT_SHIFT_X_FACTOR * LINEUP_CARD_WIDTH)

# 阵容界面头像明显比仓库里小，为了匹配稳定，
# 这里专门为阵容识别准备一套“更偏向缩小”的多尺度列表。
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
    识别卡片中的英雄 ID（阵容/爬塔入口）。
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
    识别当前通关阵容界面的 5 个角色及其“高/低/未拥有”：
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
        # 1. 优先选择“识别到 5 个角色”的布局；
        # 2. 如果两套都不是 5 个，则保留识别数量更多的那套；
        # 3. 数量相同则保留先出现的（保持原有行为为主）。
        if recognized_count == 5:
            best_lineup = lineup_heroes
            best_debug_path = debug_path
            best_count = recognized_count
            # 已经满足“5 个角色全识别”，可以直接结束循环
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
    - 请手动停留在“查看通关阵容界面”；
    - 直接运行本脚本，将：
        * 估算 5 个阵容头像框的位置并画绿框截一张调试大图；
        * 对每个槽位调用 has_fancy_border + _recognize_hero；
        * 在控制台打印「槽位索引 / 英雄 ID / 花边状态 / 边缘像素数」；
        * 检测手动战斗标志并输出得分和截图。
    """
    init_templates_from_dir()

    # 检测手动战斗标志
    print("\n========== 手动战斗标志检测 ==========")
    score_g, pos_g = check_artificial_score(threshold=0.7)
    print(f"手动战斗标志匹配得分: {score_g:.3f}, 是否检测到: {pos_g is not None}")
    
    if DEBUG_MODE:
        img = screenshot_bgr()
        vis = img.copy()
        if pos_g:
            x, y = pos_g
            cv2.rectangle(vis, (x - 30, y - 15), (x + 30, y + 15), (0, 0, 255), 2)
            cv2.putText(vis, f"g:{score_g:.2f}", (x - 30, y - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
        debug_path = os.path.join(DEBUG_DIR, f"artificial_check_{int(time.time())}.png")
        os.makedirs(DEBUG_DIR, exist_ok=True)
        cv2.imwrite(debug_path, vis)
        print(f"手动战斗标志检测截图已保存: {debug_path}")
    print("=====================================\n")

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


def select_lineup(start_index: int):
    """
    在“通关阵容界面”里，从编号 start_index 开始往后找可用阵容。

    编号规则（0 开始）：
    - 假设当前界面初始显示的是第 0 套阵容；
    - 进入界面后，先点击 right(h) 若干次，把光标移到 start_index 对应的阵容；
    - 然后从 start_index 开始循环：
        - 如果这一套阵容含有手动战斗标志 artificial(g)：用 right(h) 切到下一套，index += 1
        - 如果这一套阵容不含 g：点击 oneclick(i) 采用，返回当前 index
        - 如果想切下一套但已经没有 right(h) 可点：说明已经是最后一套，
          仍然点击 oneclick(i) 采用，并返回 None，表示“到头了”。

    返回：
        - int: 采用的阵容编号（>= start_index）
        - None: 没有更多新阵容（已经到最后一套）
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
            print("阵容数量不足以跳到指定起点，直接返回 None。")
            return None
        current_index += 1
        time.sleep(0.5)
        random_sleep()

    # 2. 从 current_index（>= start_index）开始往后找"没有 g 且练度满足要求 的阵容"
    # 等待界面完全加载
    time.sleep(1.0)
    
    while True:
        print(f"检查阵容编号 {current_index} 是否含有手动战斗标志 g。")
        score_g, pos_g = check_artificial_score(threshold=0.7)
        print(f"手动战斗标志匹配得分: {score_g:.3f}, 是否检测到: {pos_g is not None}")
        
        # 调试模式：保存手动战斗标志检测截图
        if DEBUG_MODE:
            img = screenshot_bgr()
            vis = img.copy()
            if pos_g:
                x, y = pos_g
                cv2.rectangle(vis, (x - 30, y - 15), (x + 30, y + 15), (0, 0, 255), 2)
                cv2.putText(vis, f"g:{score_g:.2f}", (x - 30, y - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
            debug_path = os.path.join(DEBUG_DIR, f"artificial_check_{int(time.time())}.png")
            os.makedirs(DEBUG_DIR, exist_ok=True)
            cv2.imwrite(debug_path, vis)
            print(f"手动战斗标志检测截图已保存: {debug_path}")

        if not pos_g:
            # 没有 g，继续做练度匹配判断
            hero_levels = _load_warehouse_levels()
            lineup_heroes, _debug_path = _recognize_lineup_with_levels()
            if _is_lineup_acceptable(hero_levels, lineup_heroes):
                if not wait_and_click(tpl_oneclick, f"oneclick(i) 采用阵容 {current_index}", 0.8):
                    return None
                random_sleep()
                
                # 点击一键采用后，等待一段时间检测是否出现 not owned.png
                time.sleep(1.0)
                pos_not_owned = find_center_silent(tpl_not_owned, threshold=0.8)
                
                if pos_not_owned:
                    # 检测到 not owned.png，说明该阵容不可用，点击取消并继续检查下一个阵容
                    print(f"阵容 {current_index} 检测到未拥有标志，点击取消并跳过。")
                    if not wait_and_click(tpl_quxiao, "quxiao(m) 取消当前阵容", 0.8):
                        print("点击取消失败，跳过当前阵容。")
                    random_sleep()
                    # 等待返回阵容选择界面
                    time.sleep(1.0)
                    # 继续检查下一个阵容
                    print(f"阵容 {current_index} 不可用，尝试切到下一套。")
                    if not wait_and_click(tpl_right, f"right(h) 从阵容 {current_index} 切到下一套", 0.8):
                        # 点不到 right 说明已经是最后一套
                        print("已经是最后一套阵容，且检测到未拥有标志，直接返回 None。")
                        return None
                    current_index += 1
                    time.sleep(0.5)
                    random_sleep()
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
            print("已经是最后一套阵容，且含 g，直接返回 None。")
            return None

        current_index += 1
        time.sleep(0.5)
        random_sleep()


def flow_tower():
    """
    功能：爬塔

    入口：当前在战斗界面（可直接点击 patatiaozhan）。

    - 点击 patatiaozhan 进入战斗界面
    - 在战斗界面：
        * 点击 autocha 自动挑战；
        * 等待战斗结果（成功或失败）：
            - 失败：进入阵容选择逻辑
            - 成功：点击 end 回到关卡界面，重新开始
        * 监控挂机托管标志判断是否正在战斗
    """
    # 预先加载一次模板和仓库练度，后续在 select_lineup 中会再次读取最新文本
    init_templates_from_dir()

    have_custom_lineup = False     # 是否已经从阵容界面选过阵容
    current_lineup_index = -1      # 当前阵容编号（初始为 -1，表示还没选过）
    current_lineup_fail = 0        # 当前阵容连续失败次数

    # 战斗监控函数
    def monitor_battle():
        """监控战斗状态，返回战斗结果"""
        last_seen_guaji = time.time()
        while True:
            hit = wait_for_any(
                [(tpl_fail, "fail"), (tpl_end, "end")],
                threshold=0.8,
                timeout=5.0,
                interval=1.0,
            )
            if hit:
                return hit

            pos_guaji = find_center_silent(tpl_zidongtiaozhanzhong, threshold=0.8)
            if pos_guaji:
                last_seen_guaji = time.time()

            now = time.time()
            if (now - last_seen_guaji) > 180:
                print(
                    "超过 3 分钟未检测到自动挑战中标志 zidongtiaozhanzhong.png，"
                    "且未检测到失败标志 fail/end，无法判断当前状态，结束本次爬塔流程。"
                )
                return None

    # 主循环
    while True:
        # 1. 点击 patatiaozhan 进入战斗界面
        if not wait_and_click(tpl_patatiaozhan, "patatiaozhan", 0.8):
            print("未找到 patatiaozhan，认为已经推完，尝试点击 exit 退出。")
            # 尝试点击 exit 退出（只需要点击一次，因为已经在关卡界面）
            if not wait_and_click(tpl_exit, "exit", 0.8):
                print("点击 exit 失败，爬塔流程结束。")
                return False
            random_sleep()
            print("已经推完，成功退出爬塔流程。")
            return True
        random_sleep()

        # 2. 在战斗界面点击 autocha 自动挑战
        if not wait_and_click(tpl_autocha, "autocha", 0.8):
            print("未找到 autocha，爬塔流程结束。")
            return False
        random_sleep()

        # 3. 等待战斗结果
        hit = monitor_battle()
        if hit is None:
            return True

        hit_tpl, hit_name, _ = hit
        if hit_tpl == tpl_end:
            # 图 end：通过一段关卡后失败，不应计入“同一关连续失败”
            current_lineup_fail = 0
            current_lineup_index = -1  # 重置阵容编号
            have_custom_lineup = False  # 标记为未选择阵容
            print("检测到 end：重置当前阵容连续失败次数、阵容编号，并重新进入关卡界面。")
            if not wait_and_click(tpl_end, "end_click", 0.8):
                print("点击 end 失败，退出爬塔。")
                return False
            random_sleep()
            # 点击 end 后会回到关卡界面，需要重新点击 patatiaozhan
            continue

        # 4. 检测到失败图 fail 后，点击 repeat 回到关卡界面
        if not wait_and_click(tpl_repeat, "repeat", 0.8):
            print("点击 repeat 失败，退出爬塔。")
            return False
        random_sleep()

        # 5. 阵容调整逻辑
        if not have_custom_lineup:
            # 第一次失败：先进入阵容界面，从 0 开始选一套“无 g 的阵容”
            if not wait_and_click(tpl_lineup, "lineup_first", 0.8):
                print("点击 lineup 进入通关阵容界面失败。")
                return False
            random_sleep()

            idx = select_lineup(start_index=0)
            if idx is None:
                # 阵容用尽或异常，退出爬塔
                print("没有更多可选阵容，退出爬塔。")
                # 识别并点击点击空白处关闭按钮退出阵容界面
                if not wait_and_click(tpl_dianjikongbaichuguanbi, "dianjikongbaichuguanbi", 0.8):
                    print("未找到点击空白处关闭按钮，尝试点击一键采用按钮右边位置")
                    # 先识别一键采用按钮，然后点击右边区域退出阵容界面
                    pos_oneclick = find_center(tpl_oneclick, threshold=0.8)
                    if pos_oneclick:
                        x, y = pos_oneclick
                        # 点击一键采用按钮右边 200 像素的位置
                        send_coord(x + 200, y)
                    else:
                        print("未找到一键采用按钮，尝试点击固定位置")
                        send_coord(100, 500)
                random_sleep()
                wait_and_click(tpl_exit, "exit", 0.8)
                random_sleep()
                wait_and_click(tpl_exit, "exit", 0.8)
                return False

            have_custom_lineup = True
            current_lineup_index = idx
            current_lineup_fail = 0
            print(f"首次选定阵容编号 {current_lineup_index}，接下来用该阵容爬塔。")
            random_sleep()
        
        # 6. 用选定的阵容继续战斗
        while True:
            # 直接点击 autocha 进行自动挑战
            if not wait_and_click(tpl_autocha, "autocha_after_lineup", 0.8):
                print("未找到 autocha，爬塔流程结束。")
                return False
            random_sleep()
            
            # 监控战斗状态
            hit = monitor_battle()
            if hit is None:
                return True

            hit_tpl, hit_name, _ = hit
            if hit_tpl == tpl_end:
                current_lineup_fail = 0
                current_lineup_index = -1
                have_custom_lineup = False
                print("检测到 end：重置当前阵容连续失败次数、阵容编号，并重新进入关卡界面。")
                if not wait_and_click(tpl_end, "end_click", 0.8):
                    print("点击 end 失败，退出爬塔。")
                    return False
                random_sleep()
                # 跳出循环，回到主循环重新点击 patatiaozhan
                break

            # 再次失败，点击 repeat 回到关卡界面
            if not wait_and_click(tpl_repeat, "repeat_after_lineup", 0.8):
                print("点击 repeat 失败，退出爬塔。")
                return False
            random_sleep()
            
            # 累加失败次数
            current_lineup_fail += 1
            print(f"当前阵容 {current_lineup_index} 连续失败次数: {current_lineup_fail}")
            
            if current_lineup_fail < 3:
                # 还不到 3 次，继续用当前阵容重试
                continue

            # 同一阵容失败 3 次：再进入阵容界面，从下一套开始找
            if not wait_and_click(tpl_lineup, "lineup_again", 0.8):
                print("再次点击 lineup 进入通关阵容界面失败。")
                return False
            random_sleep()

            next_start = current_lineup_index + 1
            idx = select_lineup(start_index=next_start)
            if idx is None:
                # 已经没有新的阵容可选：采用后退出爬塔到最外层
                print("没有更多可选阵容，退出爬塔。")
                # 识别并点击点击空白处关闭按钮退出阵容界面
                if not wait_and_click(tpl_dianjikongbaichuguanbi, "dianjikongbaichuguanbi", 0.8):
                    print("未找到点击空白处关闭按钮，尝试点击一键采用按钮右边位置")
                    # 先识别一键采用按钮，然后点击右边区域退出阵容界面
                    pos_oneclick = find_center(tpl_oneclick, threshold=0.8)
                    if pos_oneclick:
                        x, y = pos_oneclick
                        # 点击一键采用按钮右边 200 像素的位置
                        send_coord(x + 200, y)
                    else:
                        print("未找到一键采用按钮，尝试点击固定位置")
                        send_coord(100, 500)
                random_sleep()
                wait_and_click(tpl_exit, "exit", 0.8)
                random_sleep()
                wait_and_click(tpl_exit, "exit", 0.8)
                return False

            current_lineup_index = idx
            current_lineup_fail = 0
            print(f"切换到新阵容编号 {current_lineup_index}，失败计数清零。")
            random_sleep()


if __name__ == "__main__":
    if DEBUG_MODE:
        # 调试模式：仅调试阵容识别
        # 请手动进入"查看通关阵容界面"后，再直接运行本脚本。
        debug_lineup_recognition()
    else:
        # 正常模式：执行爬塔功能
        flow_tower()