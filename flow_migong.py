"""
迷宫自动挑战脚本
一次性进入 → 外层循环(挑战次数) → 布阵 → 战斗 → 内层循环(逐层事件) → shouling → 完成
"""
import json
import time

from common import (
    find_center,
    get_resource_path,
    get_template_path,
    screenshot_bgr,
    send_coord,
    wait_and_click,
)
from drag_utils import send_drag
from formation import deploy_formation
from warehouse import HERO_TEMPLATES, init_templates_from_dir

# ============================================================
# 配置
# ============================================================
_config = None

# GUI 传入的运行时参数
_run_params = {}

def load_config():
    global _config
    with open(get_resource_path("migong_config.json"), encoding="utf-8") as f:
        _config = json.load(f)
    return _config

def cfg(key, default=None):
    if key in _run_params:
        return _run_params[key]
    if _config is None:
        load_config()
    return _config.get(key, default)

# ============================================================
# 模板路径
# ============================================================
def tpl(name):
    return get_template_path(name + ".png", subdir="migong")

def tpl_root(name):
    return get_template_path(name + ".png")

# ============================================================
# 辅助函数
# ============================================================
def find_mg(name, threshold=None):
    if threshold is None:
        threshold = cfg("thresholds", {}).get("default", 0.8)
    return find_center(tpl(name), threshold)

def click_mg(name, label=None, threshold=None, timeout=None):
    if label is None:
        label = name
    if threshold is None:
        threshold = cfg("thresholds", {}).get("default", 0.8)
    return wait_and_click(tpl(name), label, threshold, timeout=timeout)

def click_root(name, label=None, threshold=0.8):
    if label is None:
        label = name
    return wait_and_click(tpl_root(name), label, threshold)

def find_any_mg(names, threshold=None):
    """同时检测多个模板，返回第一个匹配的 (name, (x,y)) 或 (None, None)"""
    if threshold is None:
        threshold = cfg("thresholds", {}).get("default", 0.8)
    for name in names:
        pos = find_center(tpl(name), threshold)
        if pos is not None:
            return name, pos
    return None, None

def find_all_mg(names, threshold=None):
    """检测所有模板，返回匹配到的 {name: (x,y)}"""
    if threshold is None:
        threshold = cfg("thresholds", {}).get("default", 0.8)
    found = {}
    for name in names:
        pos = find_center(tpl(name), threshold)
        if pos is not None:
            found[name] = pos
    return found


def find_all_mg_fast(names, threshold=None, img=None):
    """一次截图匹配全部模板（用于高频轮询场景）"""
    import cv2
    if threshold is None:
        threshold = cfg("thresholds", {}).get("default", 0.8)
    if img is None:
        img = screenshot_bgr()
    found = {}
    for name in names:
        template = cv2.imread(tpl(name), cv2.IMREAD_COLOR)
        if template is None:
            continue
        res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val >= threshold:
            h, w = template.shape[:2]
            cx = max_loc[0] + w // 2
            cy = max_loc[1] + h // 2
            found[name] = (cx, cy)
    return found

def wait_mg(name, timeout=None, threshold=None):
    """等待模板出现，返回坐标或 None"""
    if threshold is None:
        threshold = cfg("thresholds", {}).get("default", 0.8)
    t = timeout or cfg("timeouts", {}).get("battle", 180)
    start = time.time()
    while time.time() - start < t:
        pos = find_mg(name, threshold)
        if pos is not None:
            return pos
        time.sleep(0.5)
    return None

def wait_any_mg(names, timeout=None, threshold=None):
    """等待多个模板中任意一个出现"""
    if threshold is None:
        threshold = cfg("thresholds", {}).get("default", 0.8)
    t = timeout or cfg("timeouts", {}).get("battle", 180)
    start = time.time()
    while time.time() - start < t:
        for name in names:
            pos = find_mg(name, threshold)
            if pos is not None:
                return name, pos
        time.sleep(0.5)
    return None, None


# ============================================================
# 稳定跳转辅助（冷却期 + 双检测 + 自动重试）
# ============================================================
def _find_root(name, threshold=None):
    if threshold is None:
        threshold = cfg("thresholds", {}).get("default", 0.8)
    return find_center(tpl_root(name), threshold)


def click_and_wait(click_name, next_name, timeout=10, cooldown=0.8,
                   click_finder=None, next_finder=None):
    """
    点击 A → 轮询检测 B → 冷却期后双检 A+B，A 仍在则重试。
    timeout: 单次尝试超时（默认10s，覆盖慢加载空窗期）
    cooldown: 冷却期（0.8s，覆盖 A 残留/渐变消失）
    """
    if click_finder is None:
        click_finder = find_mg
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


# ============================================================
# 战斗 + 跳过后处理
# ============================================================
def do_battle_and_skip(zhandou_retries=0):
    """
    点击 zhandou → 等待战斗结束 → tiaoguo → 结算
    含 shaoren 检测和 zhandou 重试（用于战斗无法开始的失败判断）
    返回: "normal" / "fail" / "no_zhandou"
    """
    print("  点击战斗")
    zd_pos = wait_mg("zhandou", timeout=15)
    if zd_pos is None:
        print("  未找到战斗按钮")
        return "no_zhandou"
    send_coord(zd_pos[0], zd_pos[1])
    time.sleep(0.8)
    send_coord(zd_pos[0], zd_pos[1])

    # 等待战斗结束，启用 zhandou_retries 时同时检测 zhandou 重新出现（战斗没开起来）
    battle_timeout = cfg("timeouts", {}).get("battle", 180)
    retry_count = 0
    battle_result = None
    result_pos = None
    overall_start = time.time()

    while time.time() - overall_start < battle_timeout:
        found_name, found_pos = wait_any_mg(["tiaoguo", "shaoren"], timeout=10)
        if found_name is not None:
            battle_result = found_name
            result_pos = found_pos
            break

        # zhandou 重新出现 = 战斗失败，重试点击
        if zhandou_retries > 0:
            zd_still = find_mg("zhandou")
            if zd_still is not None:
                if retry_count < zhandou_retries:
                    retry_count += 1
                    print(f"  zhandou 仍在，重试点击 ({retry_count}/{zhandou_retries})")
                    send_coord(zd_still[0], zd_still[1])
                    time.sleep(0.8)
                    send_coord(zd_still[0], zd_still[1])
                else:
                    print("  zhandou 重试耗尽，判定战斗失败")
                    return "fail"

    if battle_result is None:
        if zhandou_retries > 0:
            return "fail"
        return "no_zhandou"

    if battle_result == "shaoren":
        print("  ⚠ 检测到少人")
        time.sleep(0.5)
        click_mg("migongqueren", "migongqueren(少人)")
        time.sleep(0.5)
        click_mg("tiaoguo", "tiaoguo(少人)")
        time.sleep(0.3)
    else:
        print("  点击跳过")
        send_coord(result_pos[0], result_pos[1])
        time.sleep(0.3)

    # 等待结算画面
    close_pos = wait_mg("dianjikongbaiguanbi", timeout=15)
    if close_pos:
        print("  识别到空白关闭，等待1.5s后点击")
        time.sleep(1.5)
        send_coord(close_pos[0], close_pos[1])
        time.sleep(0.8)
        send_coord(close_pos[0], close_pos[1])
    else:
        print("  结算画面超时，重试点击...")
        click_mg("dianjikongbaiguanbi", "dianjikongbaiguanbi(兜底)")
    return "normal"


# ============================================================
# 多实例检测辅助
# ============================================================
def find_all_instances_mg(name, threshold=None, min_gap=30, img=None):
    """检测屏幕上模板的多个实例，返回 [(x, y), ...]，按 y 坐标升序"""
    import cv2
    if threshold is None:
        threshold = cfg("thresholds", {}).get("default", 0.8)
    tpl_path = tpl(name)
    template = cv2.imread(tpl_path, cv2.IMREAD_COLOR)
    if template is None:
        return []
    th, tw = template.shape[:2]
    if img is None:
        img = screenshot_bgr()
    res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
    loc = []
    h, w = res.shape[:2]
    for y in range(h):
        for x in range(w):
            if res[y, x] >= threshold:
                cx, cy = x + tw // 2, y + th // 2
                too_close = False
                for ex, ey in loc:
                    if abs(cx - ex) < min_gap and abs(cy - ey) < min_gap:
                        too_close = True
                        break
                if not too_close:
                    loc.append((cx, cy))
    loc.sort(key=lambda p: p[1])  # 按 y 从上到下
    return loc


# ============================================================
# 烙印选取
# ============================================================
def handle_brand_selection():
    """
    识别 xuanze → 优先处理 shishi → 然后按列表1 → 列表2
    返回 True 如果处理了选择，False 如果没检测到选择界面
    """
    # 等待 xuanze 画面出现
    print("  → 检查是否需要烙印选取...")
    xuanze_pos = wait_mg("xuanze", timeout=cfg("timeouts", {}).get("xuanze", 5),
                         threshold=cfg("thresholds", {}).get("xuanze", 0.7))
    if xuanze_pos is None:
        print("  → 未检测到烙印选取画面")
        return False

    print("  → 烙印选取")
    selected = False

    # 优先检查 shishi
    shishi_list = find_all_instances_mg("shishi")
    if shishi_list:
        print(f"    检测到 {len(shishi_list)} 个 shishi")
        overflow_pos = find_mg("yichufangyu")

        if overflow_pos is not None:
            print("    选中: yichufangyu(溢出防御)")
            send_coord(overflow_pos[0], overflow_pos[1])
            selected = True
        elif len(shishi_list) == 1:
            print(f"    选中: 单个 shishi ({shishi_list[0][0]}, {shishi_list[0][1]})")
            send_coord(shishi_list[0][0], shishi_list[0][1])
            selected = True
        else:
            topmost = shishi_list[0]
            print(f"    选中: 最上方 shishi ({topmost[0]}, {topmost[1]})")
            send_coord(topmost[0], topmost[1])
            selected = True

    # 列表1
    if not selected:
        brand_list_1 = cfg("brand_list_1", [])
        for brand_name in brand_list_1:
            pos = find_mg(brand_name)
            if pos is not None:
                print(f"    选中烙印(列表1): {brand_name}")
                send_coord(pos[0], pos[1])
                selected = True
                break

    # 重置 → 等待 migongqueren → 列表2
    if not selected:
        print("    列表1未找到，点击重置")
        click_mg("chongzhi", "chongzhi")
        time.sleep(0.3)

        # 检查 migongqueren
        mgqr_pos = find_mg("migongqueren")
        if mgqr_pos is not None:
            print("    识别到 migongqueren，点击")
            send_coord(mgqr_pos[0], mgqr_pos[1])
            time.sleep(0.3)
        else:
            print("    未识别到 migongqueren，等待中...")
            mgqr_pos = wait_mg("migongqueren", timeout=3)
            if mgqr_pos is not None:
                print("    延迟识别到 migongqueren，点击")
                send_coord(mgqr_pos[0], mgqr_pos[1])
                time.sleep(0.3)
            else:
                print("    仍未识别到 migongqueren，继续")

        # 列表2
        brand_list_2 = cfg("brand_list_2", [])
        for brand_name in brand_list_2:
            pos = find_mg(brand_name)
            if pos is not None:
                print(f"    选中烙印(列表2): {brand_name}")
                send_coord(pos[0], pos[1])
                selected = True
                break

    # 列表2也未命中 → 找最上方 zise → 最上方 lanse
    if not selected:
        for color_tag, color_name in [("zise", "紫色"), ("lanse", "蓝色")]:
            instances = find_all_instances_mg(color_tag)
            if instances:
                topmost = min(instances, key=lambda p: p[1])
                print(f"    选中最上方{color_name}烙印 ({topmost[0]}, {topmost[1]})")
                send_coord(topmost[0], topmost[1])
                selected = True
                break

    # 点击确认
    time.sleep(0.3)
    click_mg("queren", "queren(烙印确认)")
    return True


# ============================================================
# 找离指定坐标最近的 migongzhandou
# ============================================================
def _pick_closest_mgzd(ex, ey, mgzds=None):
    """找到离 (ex,ey) 最近的 migongzhandou 坐标"""
    if mgzds is None:
        mgzds = find_all_instances_mg("migongzhandou")
    if not mgzds:
        return None
    best = min(mgzds, key=lambda m: ((m[0] - ex) ** 2 + (m[1] - ey) ** 2) ** 0.5)
    return best


# ============================================================
# 逐层事件处理（内层循环）
# ============================================================
def handle_floor_events():
    """
    内层循环：逐层处理事件，直到检测到 shouling
    返回: (result_type, pos)
    """
    idle_count = 0
    max_idle = cfg("max_idle_cycles", 10)
    overall_start = time.time()
    overall_timeout = cfg("timeouts", {}).get("floor_events", 600)

    while True:
        if time.time() - overall_start > overall_timeout:
            print("逐层事件整体超时，退出")
            return "fail", None

        # 扫描当前屏幕所有事件和特殊标记
        event_names = cfg("event_priority", [])
        special_events = ["jingying", "shouling", "shencengshouling",
                          "laoyinjingqiu", "shangdian", "shuangbeijiangli"]
        all_check = list(set(event_names + special_events))

        # 一次截图，复用给事件扫描和 migongzhandou 实例检测
        img = screenshot_bgr()
        found = find_all_mg_fast(all_check, img=img)
        mgzds = find_all_instances_mg("migongzhandou", img=img)

        # 检查 shouling（最高优先级退出信号）
        if "shouling" in found:
            print("检测到 shouling")
            return "shouling", found["shouling"]

        # 检查 shencengshouling
        if "shencengshouling" in found:
            print("检测到 shencengshouling")
            return "shencengshouling", found["shencengshouling"]

        # 分离普通事件和特殊事件
        regular_found = {k: v for k, v in found.items() if k in event_names}

        # 二选一特殊事件: laoyinjingqiu + shangdian（入口不是 migongzhandou）
        has_laoyin = "laoyinjingqiu" in found
        has_shangdian = "shangdian" in found

        if has_laoyin and has_shangdian:
            print("特殊事件: laoyinjingqiu + shangdian → 进入商店")
            click_mg("goumai", "goumai(商店入口)")
            time.sleep(3.0)
            handle_shop()
            idle_count = 0
            continue

        # 独立事件: jingying
        if "jingying" in found:
            print("独立事件: jingying")
            mg_pos = _pick_closest_mgzd(found["jingying"][0], found["jingying"][1], mgzds)
            if mg_pos:
                send_coord(mg_pos[0], mg_pos[1])
                result = do_battle_and_skip()
                if result == "fail":
                    return "fail", None
                if result == "no_zhandou":
                    idle_count += 1
                    if idle_count >= max_idle:
                        print(f"连续 {idle_count} 次空闲，退出")
                        return "fail", None
                    time.sleep(2.0)
                else:
                    idle_count = 0
                handle_brand_selection()
            continue

        # shuangbeijiangli 最高优先级（覆盖所有普通事件）
        if "shuangbeijiangli" in found:
            print("shuangbeijiangli 最高优先")
            mg_pos = _pick_closest_mgzd(found["shuangbeijiangli"][0], found["shuangbeijiangli"][1], mgzds)
            if mg_pos:
                send_coord(mg_pos[0], mg_pos[1])
                result = do_battle_and_skip()
                if result == "fail":
                    return "fail", None
                if result == "no_zhandou":
                    idle_count += 1
                    if idle_count >= max_idle:
                        print(f"连续 {idle_count} 次空闲，退出")
                        return "fail", None
                    time.sleep(2.0)
                else:
                    idle_count = 0
                handle_brand_selection()
            continue

        # 普通事件：按优先级选，找最近 migongzhandou
        if regular_found:
            selected_name = None
            selected_pos = None
            for pname in event_names:
                if pname in regular_found:
                    selected_name = pname
                    selected_pos = regular_found[pname]
                    break

            if selected_pos:
                print(f"选中事件: {selected_name}（优先级最高）")
                mg_pos = _pick_closest_mgzd(selected_pos[0], selected_pos[1], mgzds)
                if mg_pos:
                    print(f"  最近 migongzhandou: ({mg_pos[0]}, {mg_pos[1]})")
                    send_coord(mg_pos[0], mg_pos[1])
                else:
                    # 找不到 migongzhandou，直接点事件
                    send_coord(selected_pos[0], selected_pos[1])
                result = do_battle_and_skip()
                if result == "fail":
                    return "fail", None
                if result == "no_zhandou":
                    idle_count += 1
                    if idle_count >= max_idle:
                        print(f"连续 {idle_count} 次空闲，退出")
                        return "fail", None
                    time.sleep(2.0)
                else:
                    idle_count = 0
                handle_brand_selection()
            continue

        # 没检测到事件
        idle_count += 1
        if idle_count >= max_idle:
            print(f"连续 {idle_count} 次无事件，退出")
            return "fail", None
        time.sleep(0.5)


# ============================================================
# 商店购买逻辑
# ============================================================
def handle_shop():
    """按优先级购买（最多 shop_max_items 个），买完点 jixuqianjin"""
    print("  [商店] 开始购买")
    shop_priority = cfg("shop_priority", [])
    max_items = cfg("shop_max_items", 2)
    bought = 0

    for item_name in shop_priority:
        if bought >= max_items:
            break
        pos = find_mg(item_name)
        if pos is not None:
            print(f"    购买: {item_name}")
            send_coord(pos[0], pos[1])
            time.sleep(0.3)
            click_mg("goumai2", "goumai2")
            time.sleep(0.5)
            # 购买后烙印选取
            if not handle_brand_selection():
                print("    未检测到烙印选择，跳过，继续购买下一个")
            bought += 1
            time.sleep(3.0)
        else:
            print(f"    未找到商品: {item_name}，跳过")

    print(f"  [商店] 购买完成，共{bought}件")
    click_mg("jixuqianjin", "jixuqianjin")
    time.sleep(0.5)


# ============================================================
# 失败处理
# ============================================================
def handle_failure(challenges_left_func):
    """战斗失败后的处理流程"""
    print("  [失败处理]")

    # 点击空白处关闭
    click_mg("dianjikongbaiguanbi", "dianjikongbaiguanbi(失败)")
    time.sleep(0.5)
    # 点击结束探索
    click_mg("jieshutansuo2", "jieshutansuo2")
    time.sleep(0.5)
    # 长按 changanjieshu（4s 按住，同布阵拖拽重复次数）
    print("    等待 changanjieshu...")
    cj_pos = wait_mg("changanjieshu", timeout=5)
    if cj_pos is not None:
        drag_rpt = cfg("drag_repeat", 2)
        for i in range(drag_rpt):
            send_drag(cj_pos[0], cj_pos[1], cj_pos[0], cj_pos[1], hold_ms=4000)
            if i < drag_rpt - 1:
                time.sleep(0.3)
    # 等待并点击 likaimigong
    print("    等待 likaimigong...")
    likai_pos = wait_mg("likaimigong", timeout=10)
    if likai_pos is not None:
        send_coord(likai_pos[0], likai_pos[1])
    time.sleep(1.0)

    # 挑战次数 -1
    return challenges_left_func()


# ============================================================
# 外层循环中的一次挑战
# ============================================================
def _deploy_and_battle(form_name, drag_rpt, label=""):
    """布阵 → zhandou → 等待战斗结束 → tiaoguo → 检查失败 → dianjikongbaiguanbi → 烙印选取"""
    click_mg("caidan", f"caidan{label}")
    time.sleep(0.3)
    click_mg("xiexia", f"xiexia{label}")
    time.sleep(0.5)
    init_templates_from_dir()
    deploy_formation(form_name, HERO_TEMPLATES, drag_repeat=drag_rpt)
    time.sleep(0.5)
    zd_pos = wait_mg("zhandou", timeout=5)
    if zd_pos:
        send_coord(zd_pos[0], zd_pos[1])
        time.sleep(0.8)
        send_coord(zd_pos[0], zd_pos[1])

    # 等待战斗结束（与 do_battle_and_skip 一致）
    battle_result, result_pos = wait_any_mg(["tiaoguo", "shaoren"], timeout=cfg("timeouts", {}).get("battle", 180))

    if battle_result == "shaoren":
        print("  ⚠ 检测到少人")
        time.sleep(0.5)
        click_mg("migongqueren", "migongqueren(少人)")
        time.sleep(0.5)
        # 确认后重新找 tiaoguo 点击（不能用 result_pos，那是 shaoren 的坐标）
        click_mg("tiaoguo", f"tiaoguo{label}(少人)")
        time.sleep(0.3)
        # 少人处理完落到正常结算流程
    else:
        print("  点击跳过")
        # result_pos 是 tiaoguo 的坐标，直接点
        send_coord(result_pos[0], result_pos[1])
        time.sleep(0.3)

    # 等待结算画面（dianjikongbaiguanbi 或 zhandoushibai）
    end_found, end_pos = wait_any_mg(["dianjikongbaiguanbi", "zhandoushibai"], timeout=15)
    if end_found == "zhandoushibai":
        print("  ⚠ 战斗失败")
        return "fail"
    if end_found == "dianjikongbaiguanbi":
        print("  识别到空白关闭，等待1.5s后点击")
        time.sleep(1.5)
        send_coord(end_pos[0], end_pos[1])
        time.sleep(0.8)
        send_coord(end_pos[0], end_pos[1])
    else:
        print("  结算画面超时，重试点击...")
        click_mg("dianjikongbaiguanbi", f"dianjikongbaiguanbi{label}(兜底)")
    handle_brand_selection()
    return "normal"


def run_one_challenge():
    """执行一次完整的迷宫挑战"""
    form_name = cfg("formation_name", "阵容1")
    drag_rpt = cfg("drag_repeat", 2)

    # ① 进入迷宫
    print("\n=== 进入迷宫 ===")
    click_mg("jinru", "jinru")
    time.sleep(0.5)
    click_mg("migongqueren", "migongqueren(进入)", timeout=5)
    time.sleep(1.0)

    # ② 初始布阵
    print("=== 初始布阵 ===")
    click_mg("migongzhandou", "migongzhandou(布阵)")
    time.sleep(0.5)
    click_mg("caidan", "caidan")
    time.sleep(0.3)
    click_mg("xiexia", "xiexia")
    time.sleep(0.5)

    init_templates_from_dir()
    deploy_formation(form_name, HERO_TEMPLATES, deselect_offset_y=-50, drag_repeat=drag_rpt)
    time.sleep(0.5)

    # ③ 战斗
    print("=== 首次战斗 ===")
    result = do_battle_and_skip()
    if result == "fail":
        return "fail"

    # ④ 内层循环
    print("=== 逐层事件 ===")
    result, pos = handle_floor_events()
    if result == "fail":
        return "fail"

    # ⑤ shouling / shencengshouling 处理
    shouling_type = result  # "shouling" or "shencengshouling"
    print(f"=== {shouling_type} ===")

    click_mg("migongzhandou", f"migongzhandou({shouling_type})")

    if shouling_type == "shencengshouling":
        # 深层首领：重新布阵 → 战斗 → 完成
        print("  深层首领 → 重新布阵")
        time.sleep(0.5)
        click_mg("caidan", "caidan(深层首领)")
        time.sleep(0.3)
        click_mg("xiexia", "xiexia(深层首领)")
        time.sleep(0.5)
        init_templates_from_dir()
        deploy_formation(cfg("shenceng_formation_name", form_name), HERO_TEMPLATES, drag_repeat=drag_rpt)
        time.sleep(0.5)
        zd_pos = wait_mg("zhandou", timeout=5)
        if zd_pos:
            send_coord(zd_pos[0], zd_pos[1])
            time.sleep(0.8)
            send_coord(zd_pos[0], zd_pos[1])
        click_mg("tiaoguo", "tiaoguo(深层首领)")
        time.sleep(0.3)
        close_pos = wait_mg("dianjikongbaiguanbi", timeout=5)
        if close_pos:
            time.sleep(1.5)
            send_coord(close_pos[0], close_pos[1])
            time.sleep(0.8)
            send_coord(close_pos[0], close_pos[1])
        handle_brand_selection()
        click_mg("tansuowancheng", "tansuowancheng")
        time.sleep(0.5)
        return "done"

    # 普通 shouling
    result = do_battle_and_skip()
    if result == "fail":
        return "fail"

    handle_brand_selection()

    action = cfg("shouling_action", "jieshutansuo")

    if action == "jieshutansuo":
        print("  → 结束探索")
        click_mg("jieshutansuo", "jieshutansuo")
        time.sleep(0.5)
        return "done"

    else:
        print("  → 继续探索")
        click_mg("jixutansuo", "jixutansuo")
        time.sleep(0.5)

        # 后续循环（计数器驱动，不再检测 shencengshouling）
        mgzd_count = 0
        while True:
            # 检测 shencengshouling（模板识别）
            shenceng_pos = find_mg("shencengshouling")
            if shenceng_pos is not None:
                print("  检测到深层首领")
                click_mg("migongzhandou", "migongzhandou(深层首领)")
                time.sleep(0.5)
                shenceng_form = cfg("shenceng_formation_name", form_name)
                if _deploy_and_battle(shenceng_form, drag_rpt, "(深层首领)") == "fail":
                    return "fail"
                click_mg("tansuowancheng", "tansuowancheng")
                time.sleep(0.5)
                return "done"

            mgzd_count += 1
            print(f"  第{mgzd_count}次 migongzhandou")

            if mgzd_count == 3:
                # 第3次：布阵（同初始）→ 战斗 → 继续
                print("  → 重新布阵(第3次，同初始)")
                click_mg("migongzhandou", f"migongzhandou(第{mgzd_count}次)")
                time.sleep(0.5)
                if _deploy_and_battle(form_name, drag_rpt, "(第3次)") == "fail":
                    return "fail"
                # 继续循环

            else:
                # 普通战斗
                click_mg("migongzhandou", f"migongzhandou(第{mgzd_count}次)")
                result = do_battle_and_skip(zhandou_retries=2)
                if result == "fail":
                    print("  [继续循环战斗失败]")
                    click_root("exit", "exit(失败)")
                    time.sleep(0.5)
                    click_mg("jieshutansuo2", "jieshutansuo2")
                    time.sleep(0.5)
                    cj_pos = wait_mg("changanjieshu", timeout=5)
                    if cj_pos is not None:
                        for i in range(drag_rpt):
                            send_drag(cj_pos[0], cj_pos[1], cj_pos[0], cj_pos[1], hold_ms=4000)
                            if i < drag_rpt - 1:
                                time.sleep(0.3)
                    likai_pos = wait_mg("likaimigong", timeout=10)
                    if likai_pos is not None:
                        send_coord(likai_pos[0], likai_pos[1])
                    time.sleep(1.0)
                    return "done"
                handle_brand_selection()


# ============================================================
# 主流程
# ============================================================
def flow_migong(challenges=1, shouling_action="jieshutansuo", formation_name="", shenceng_formation_name=""):
    """迷宫自动挑战主入口"""
    global _run_params
    _run_params = {
        "challenges": challenges,
        "shouling_action": shouling_action,
        "formation_name": formation_name,
        "shenceng_formation_name": shenceng_formation_name,
    }
    load_config()
    challenges = cfg("challenges", 3)
    print(f"迷宫自动挑战，剩余次数: {challenges}")

    # ========= 一次性进入 =========
    print("=== 一次性进入迷宫玩法 ===")
    click_and_wait("caidan", "renwu", click_finder=_find_root, next_finder=_find_root)
    # 点击 renwu → 优先检测 fanfanle2（1.5s 窗口），超时则点 fanfanle
    click_root("renwu", "renwu")
    time.sleep(0.5)
    print("  检测 fanfanle2...")
    f2_start = time.time()
    f2_found = False
    while time.time() - f2_start < 1.5:
        if _find_root("fanfanle2") is not None:
            print("  识别到 fanfanle2，跳过 fanfanle")
            f2_found = True
            break
        time.sleep(0.15)
    if not f2_found:
        click_and_wait("fanfanle", "huoqumiyao", click_finder=_find_root, next_finder=find_mg)
    click_and_wait("huoqumiyao", "yijiemigong")
    click_and_wait("yijiemigong", "qianwang")
    click_mg("qianwang", "qianwang")

    # ========= 外层循环 =========
    while challenges > 0:
        print(f"\n{'='*40}")
        print(f"剩余挑战次数: {challenges}")
        print(f"{'='*40}")

        result = run_one_challenge()

        if result == "fail":
            challenges = handle_failure(lambda challenges=challenges: challenges - 1)
            if challenges <= 0:
                break
            print(f"还有 {challenges} 次挑战，点击 jinru 继续")
            click_mg("jinru", "jinru(失败后)")
            time.sleep(0.5)
            continue

        # 正常完成
        challenges -= 1

        if challenges > 0:
            print(f"还有 {challenges} 次挑战，点击 jinru 继续")
            click_mg("jinru", "jinru(下一轮)")
            time.sleep(0.5)

    # 结束（四步退出）
    print("挑战次数用完，退出")
    click_root("exit", "exit")
    time.sleep(0.5)
    click_root("exitck", "exitck")
    time.sleep(0.5)
    click_root("exitck", "exitck2")
    time.sleep(0.5)
    click_root("exit", "exit3")
    print("迷宫脚本结束")


if __name__ == "__main__":
    flow_migong()
