from common import wait_and_click, find_center, screenshot_bgr, send_coord, get_template_path
from jiance import check_and_handle_libao
import cv2
import time
import random

# 随机等待函数，2-3秒
def random_sleep():
    time.sleep(random.uniform(2.0, 3.0))

# 静默版本的 find_center，不输出匹配得分
def find_center_silent(template_path, threshold=0.8):
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        raise ValueError(f"模板读取失败: {template_path}")
    h, w = template.shape[:2]

    img = screenshot_bgr()
    res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val < threshold:
        return None

    top_left = max_loc
    center_x = top_left[0] + w // 2
    center_y = top_left[1] + h // 2
    return center_x, center_y

# === 模板路径，对应你的文件名 ===
tpl_wanfamulu         = get_template_path("wanfamulu.png")
tpl_pujing            = get_template_path("pujing.png")
tpl_kaishitiaozhan    = get_template_path("kaishitiaozhan.png")
tpl_pujingjixutiaozhan = get_template_path("pujingjixutiaozhan.png")
tpl_pujingzhandou     = get_template_path("pujingzhandou.png")
tpl_zhandou           = get_template_path("zhandou.png")

tpl_tiaoguo           = get_template_path("tiaoguo.png")
tpl_pujingjieshu      = get_template_path("pujingjieshu.png")
tpl_mianfeimenpiao    = get_template_path("mianfeimenpiao.png")
tpl_querengoumaimenpiao = get_template_path("querengoumaimenpiao.png")
tpl_fufeimenpiao      = get_template_path("fufeimenpiao.png")
tpl_bumaifufeimenpiao = get_template_path("bumaifufeimenpiao.png")
tpl_exit              = get_template_path("exit.png")
tpl_dianjikongbaichuguanbi = get_template_path("dianjikongbaichuguanbi.png")

# 一场战斗最长等待多久（秒）
MAX_BATTLE_TIME = 180

# 等待某张图出现
def wait_for_appearance(template_path, name, threshold=0.8, timeout=MAX_BATTLE_TIME, interval=0.5):
    """循环等待某张图出现，出现返回坐标，超时返回 None。"""
    start = time.time()
    attempt = 0
    while True:
        attempt += 1
        pos = find_center_silent(template_path, threshold)
        if pos:
            print(f"{name} 出现，第 {attempt} 次检测，坐标: {pos}")
            return pos

        elapsed = time.time() - start
        if elapsed > timeout:
            print(f"{name} 在 {timeout} 秒内未出现，放弃等待。")
            return None

        time.sleep(interval)

# 等待多张图中的任意一张出现
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
                print(f"{name} 出现，第 {attempt} 次检测，坐标: {pos}")
                return template_path, name, pos

        elapsed = time.time() - start
        if elapsed > timeout:
            names = " / ".join([n for _, n in templates])
            print(f"{names} 在 {timeout} 秒内未出现，放弃等待。")
            return None

        time.sleep(interval)

# 查找多个匹配中最左边且最下面的一个
def find_leftmost(templates, threshold=0.8):
    """
    查找多个模板中最左边（x坐标最小）且最下面（y坐标最大）的一个
    
    templates: List[template_path]
    返回：
        - (template_path, name, pos) 最左边且最下面的匹配
        - None 没有匹配
    """
    matches = []
    for template_path in templates:
        pos = find_center_silent(template_path, threshold)
        if pos:
            matches.append((template_path, pos))
    
    if not matches:
        return None
    
    # 首先按x坐标排序（从小到大），然后按y坐标排序（从大到小）
    # 这样最左边且最下面的按钮会排在第一位
    matches.sort(key=lambda x: (x[1][0], -x[1][1]))
    template_path, pos = matches[0]
    
    # 根据模板路径确定名称
    name_map = {
        tpl_pujingzhandou: "pujingzhandou",
        tpl_zhandou: "zhandou",
    }
    name = name_map.get(template_path, "unknown")
    
    print(f"找到最左边且最下面的战斗按钮: {name}, 坐标: {pos}")
    return template_path, name, pos

def flow_pujing():
    """
    功能：普晶挑战

    入口：当前在游戏主界面。

    - 先点 wanfamulu 进入玩法目录界面
    - 再点 pujing 进入普晶界面
    - 点击 kaishitiaozhan 或 pujingjixutiaozhan 开始挑战
    - 识别 pujingzhandou，选择最左边的点击
    - 处理三种情况：
        1. 次数充足：进入战斗界面，点击战斗，然后点击 tiaoguo，然后点击 pujingjieshu，回到挑战界面，重复流程
        2. 识别到 mianfeimenpiao：点击 querengoumaimenpiao，再次点击挑战，然后点击战斗，然后点击 tiaoguo，然后点击 pujingjieshu，回到挑战界面，重复流程
        3. 识别到 fufeimenpiao：点击 bumaifufeimenpiao，然后点击 exit 退到玩法界面，脚本结束
    """
    # 1. 点击 wanfamulu 进入玩法目录界面
    if not wait_and_click(tpl_wanfamulu, "wanfamulu", 0.7):
        print("点击 wanfamulu 进入玩法目录界面失败。")
        return False
    random_sleep()

    # 2. 点击 pujing 进入普晶界面
    if not wait_and_click(tpl_pujing, "pujing", 0.8):
        print("点击 pujing 进入普晶界面失败。")
        return False
    random_sleep()
    
    # 3. 检测并点击 dianjikongbaichuguanbi，连续5秒不出现才进入下一步
    print("开始检测 dianjikongbaichuguanbi...")
    start_time = time.time()
    while time.time() - start_time < 5.0:
        pos = find_center_silent(tpl_dianjikongbaichuguanbi, 0.8)
        if pos:
            print("识别到 dianjikongbaichuguanbi，点击关闭")
            send_coord(pos[0], pos[1])
            random_sleep()
            # 重新开始计时
            start_time = time.time()
        else:
            # 未找到，等待0.5秒后重试
            time.sleep(0.5)
    print("连续5秒未检测到 dianjikongbaichuguanbi，进入下一步")

    # 主循环
    while True:
        # 3. 点击 kaishitiaozhan 或 pujingjixutiaozhan 开始挑战
        hit = wait_for_any(
            [(tpl_kaishitiaozhan, "kaishitiaozhan"), (tpl_pujingjixutiaozhan, "pujingjixutiaozhan")],
            threshold=0.8,
            timeout=30.0,
            interval=1.0,
        )

        if hit is None:
            print("未找到挑战按钮，普晶流程结束。")
            return False

        hit_tpl, hit_name, hit_pos = hit
        print(f"点击 {hit_name}")
        send_coord(hit_pos[0], hit_pos[1])
        random_sleep()

        # 4. 判断是开始挑战还是继续挑战
        if hit_tpl == tpl_pujingjixutiaozhan:
            # 继续挑战，直接跳过门票检测，选择战斗按钮并执行战斗
            print("识别到继续挑战，跳过门票检测，直接进入战斗流程。")
            time.sleep(1.0)
            battle_hit = find_leftmost([tpl_pujingzhandou, tpl_zhandou], threshold=0.8)
            if battle_hit is None:
                print("未找到战斗按钮，普晶流程结束。")
                return False
            battle_tpl, battle_name, battle_pos = battle_hit
            if not execute_battle_flow(battle_tpl, battle_name, battle_pos):
                return False
            # 继续下一轮循环
            continue

        # 5. 开始挑战，等待出现战斗界面或门票提示
        hit = wait_for_any(
            [(tpl_mianfeimenpiao, "mianfeimenpiao"), (tpl_fufeimenpiao, "fufeimenpiao")],
            threshold=0.8,
            timeout=3.0,
            interval=1.0,
        )

        if hit is None:
            print("未检测到门票提示，次数充足，进入战斗流程。")
            # 次数充足，选择战斗按钮并执行战斗
            time.sleep(1.0)
            battle_hit = find_leftmost([tpl_pujingzhandou, tpl_zhandou], threshold=0.8)
            if battle_hit is None:
                print("未找到战斗按钮，普晶流程结束。")
                return False
            battle_tpl, battle_name, battle_pos = battle_hit
            if not execute_battle_flow(battle_tpl, battle_name, battle_pos):
                return False
        else:
            hit_tpl, hit_name, _ = hit

            # 情况2：识别到 mianfeimenpiao
            if hit_tpl == tpl_mianfeimenpiao:
                print("识别到 mianfeimenpiao，购买免费门票。")
                # 点击 querengoumaimenpiao 确认购买
                if not wait_and_click(tpl_querengoumaimenpiao, "querengoumaimenpiao", 0.8):
                    print("点击 querengoumaimenpiao 失败，普晶流程结束。")
                    return False
                random_sleep()

                # 再次点击挑战
                hit = wait_for_any(
                    [(tpl_kaishitiaozhan, "kaishitiaozhan"), (tpl_pujingjixutiaozhan, "pujingjixutiaozhan")],
                    threshold=0.8,
                    timeout=30.0,
                    interval=1.0,
                )

                if hit is None:
                    print("未找到挑战按钮，普晶流程结束。")
                    return False

                hit_tpl, hit_name, hit_pos = hit
                print(f"点击 {hit_name}")
                send_coord(hit_pos[0], hit_pos[1])
                random_sleep()

                # 选择战斗按钮并执行战斗
                time.sleep(1.0)
                battle_hit = find_leftmost([tpl_pujingzhandou, tpl_zhandou], threshold=0.8)
                if battle_hit is None:
                    print("未找到战斗按钮，普晶流程结束。")
                    return False
                battle_tpl, battle_name, battle_pos = battle_hit
                if not execute_battle_flow(battle_tpl, battle_name, battle_pos):
                    return False

            # 情况3：识别到 fufeimenpiao
            elif hit_tpl == tpl_fufeimenpiao:
                print("识别到 fufeimenpiao，不购买付费门票。")
                # 点击 bumaifufeimenpiao 不购买
                if not wait_and_click(tpl_bumaifufeimenpiao, "bumaifufeimenpiao", 0.8):
                    print("点击 bumaifufeimenpiao 失败，普晶流程结束。")
                    return False
                random_sleep()

                # 点击 exit 退到玩法界面
                if not wait_and_click(tpl_exit, "exit", 0.8):
                    print("点击 exit 失败，普晶流程结束。")
                    return False
                random_sleep()

                # 调用 jiance.py 检测礼包弹窗
                print("开始检测礼包弹窗...")
                check_and_handle_libao()
                print("礼包弹窗检测完成")

                # 脚本结束
                print("普晶流程结束。")
                return True

            # 其他情况
            else:
                print(f"未知情况：{hit_name}，普晶流程结束。")
                return False

def execute_battle_flow(battle_tpl, battle_name, battle_pos):
    """执行战斗流程"""
    print(f"点击 {battle_name}")
    send_coord(battle_pos[0], battle_pos[1])
    random_sleep()

    # 点击 zhandou 进入战斗
    if not wait_and_click(tpl_zhandou, "zhandou", 0.8):
        print("点击 zhandou 失败，普晶流程结束。")
        return False
    random_sleep()

    # 等待战斗结束，点击 tiaoguo 跳过
    if not wait_and_click(tpl_tiaoguo, "tiaoguo", 0.8):
        print("点击 tiaoguo 失败，普晶流程结束。")
        return False
    random_sleep()

    # 等待 pujingjieshu 出现，识别到后等待3秒再点击
    pos = wait_for_appearance(tpl_pujingjieshu, "pujingjieshu", 0.8)
    if pos is None:
        print("未识别到 pujingjieshu，普晶流程结束。")
        return False
    print("识别到 pujingjieshu，等待3秒后点击...")
    time.sleep(3.0)
    send_coord(pos[0], pos[1])
    random_sleep()

    # 回到挑战界面，继续循环
    return True

if __name__ == "__main__":
    flow_pujing()
