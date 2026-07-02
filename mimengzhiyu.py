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
tpl_mimengzhiyu       = get_template_path("mimengzhiyu.png")
tpl_tiaozhan          = get_template_path("tiaozhan.png")
tpl_zhandou           = get_template_path("zhandou.png")
tpl_tiaoguozhandou    = get_template_path("tiaoguozhandou.png")
tpl_pujingjieshu      = get_template_path("pujingjieshu.png")
tpl_goumaimimeng      = get_template_path("goumaimimeng.png")
tpl_querengoumaimenpiao = get_template_path("querengoumaimenpiao.png")
tpl_cishubugou        = get_template_path("cishubugou.png")
tpl_exit              = get_template_path("exit.png")

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

# 处理战斗界面逻辑
def handle_battle():
    """处理战斗界面，优先点击tiaoguozhandou，如果没有则点击zhandou"""
    # 先检查是否存在tiaoguozhandou
    pos_tiaoguozhandou = find_center_silent(tpl_tiaoguozhandou, threshold=0.8)
    if pos_tiaoguozhandou:
        print("检测到tiaoguozhandou，优先点击。")
        send_coord(pos_tiaoguozhandou[0], pos_tiaoguozhandou[1])
        random_sleep()
    else:
        # 检查是否存在zhandou
        pos_zhandou = find_center_silent(tpl_zhandou, threshold=0.8)
        if pos_zhandou:
            print("检测到zhandou，点击。")
            send_coord(pos_zhandou[0], pos_zhandou[1])
            random_sleep()
        else:
            print("未检测到zhandou或tiaoguozhandou，处理战斗界面失败。")
            return False

    # 等待战斗结束，点击pujingjieshu，超时时间120秒
    if not wait_and_click(tpl_pujingjieshu, "pujingjieshu", 0.8, timeout=120):
        print("点击pujingjieshu失败。")
        return False
    random_sleep()

    return True

def flow_mimengzhiyu(challenge_count=None):
    """
    功能：迷梦之域挑战

    入口：当前在游戏主界面。

    参数：
        challenge_count: 挑战次数，None表示无限循环直到次数不足

    - 先点 wanfamulu 进入玩法目录界面
    - 再点 mimengzhiyu 进入迷梦之域界面
    - 再点 tiaozhan 挑战
    - 处理两个大分支：
        大分支1：
            - 小分支1：识别到 zhandou
            - 小分支2：同时识别到 zhandou 和 tiaoguozhandou，优先点击 tiaoguozhandou
            - 不管是哪个小分支，之后都点击 pujingjieshu
        大分支2：
            - 识别到 goumaimimeng
            - 点击 querengoumaimenpiao
            - 再次点击 tiaozhan
            - 此时和大分支1一样的逻辑：识别 zhandou 和 tiaoguozhandou，优先点击 tiaoguozhandou
            - 之后点击 pujingjieshu
    """
    # 1. 点击 wanfamulu 进入玩法目录界面
    if not wait_and_click(tpl_wanfamulu, "wanfamulu", 0.7):
        print("点击 wanfamulu 进入玩法目录界面失败。")
        return False
    random_sleep()

    # 2. 点击 mimengzhiyu 进入迷梦之域界面
    if not wait_and_click(tpl_mimengzhiyu, "mimengzhiyu", 0.8):
        print("点击 mimengzhiyu 进入迷梦之域界面失败。")
        return False
    random_sleep()

    # 主循环：一直执行，直到无法继续
    completed_count = 0
    while True:
        # 检查挑战次数限制
        if challenge_count is not None and completed_count >= challenge_count:
            print(f"已完成 {completed_count} 次挑战，达到设定次数，开始退出。")
            if not wait_and_click(tpl_exit, "exit", 0.8):
                print("点击 exit 失败，迷梦之域流程结束。")
                return False
            random_sleep()
            # 调用 jiance.py 检测礼包弹窗
            check_and_handle_libao()
            print("礼包弹窗检测完成")
            print("迷梦之域流程结束。")
            return True

        # 3. 点击 tiaozhan 挑战
        if not wait_and_click(tpl_tiaozhan, "tiaozhan", 0.8):
            print("点击 tiaozhan 失败，迷梦之域流程结束。")
            return False

        # 立即检查是否识别到次数不足提示（不等待，因为cishubugou会很快消失）
        pos_cishubugou = find_center_silent(tpl_cishubugou, threshold=0.8)
        if pos_cishubugou:
            print("识别到次数不足提示，点击exit退出。")
            if not wait_and_click(tpl_exit, "exit", 0.8):
                print("点击 exit 失败，迷梦之域流程结束。")
                return False
            random_sleep()
            # 调用 jiance.py 检测礼包弹窗
            check_and_handle_libao()
            print("礼包弹窗检测完成")
            print("次数用完，迷梦之域流程结束。")
            return True

        random_sleep()

        # 4. 等待出现战斗界面或购买提示
        hit = wait_for_any(
            [(tpl_zhandou, "zhandou"), (tpl_tiaoguozhandou, "tiaoguozhandou"), (tpl_goumaimimeng, "goumaimimeng")],
            threshold=0.8,
            timeout=30.0,
            interval=1.0,
        )

        if hit is None:
            print("未检测到战斗界面或购买提示，迷梦之域流程结束。")
            return False

        hit_tpl, hit_name, _ = hit

        # 大分支1：检测到战斗相关按钮
        if hit_tpl in [tpl_zhandou, tpl_tiaoguozhandou]:
            print("进入大分支1：战斗界面。")
            # 处理战斗界面
            if not handle_battle():
                return False
            # 点击pujingjieshu后，增加完成计数
            completed_count += 1
            print(f"已完成第 {completed_count} 次挑战。")
            # 点击pujingjieshu后会回到可以点击tiaozhan的界面，继续循环
        
        # 大分支2：检测到购买提示
        elif hit_tpl == tpl_goumaimimeng:
            print("进入大分支2：购买迷梦提示。")
            # 点击 querengoumaimenpiao 确认购买
            if not wait_and_click(tpl_querengoumaimenpiao, "querengoumaimenpiao", 0.8):
                print("点击 querengoumaimenpiao 失败，迷梦之域流程结束。")
                return False
            random_sleep()

            # 再次点击 tiaozhan 挑战
            if not wait_and_click(tpl_tiaozhan, "tiaozhan_again", 0.8):
                print("再次点击 tiaozhan 失败，迷梦之域流程结束。")
                return False
            random_sleep()

            # 等待战斗界面
            if not wait_for_any(
                [(tpl_zhandou, "zhandou"), (tpl_tiaoguozhandou, "tiaoguozhandou")],
                threshold=0.8,
                timeout=30.0,
                interval=1.0,
            ):
                print("未检测到战斗界面，迷梦之域流程结束。")
                return False

            # 处理战斗界面
            if not handle_battle():
                return False
            # 点击pujingjieshu后，增加完成计数
            completed_count += 1
            print(f"已完成第 {completed_count} 次挑战。")
            # 点击pujingjieshu后会回到可以点击tiaozhan的界面，继续循环
        
        # 其他情况
        else:
            print(f"未知情况：{hit_name}，迷梦之域流程结束。")
            return False

    print("迷梦之域流程结束。")
    return True


if __name__ == "__main__":
    # 执行迷梦之域功能
    flow_mimengzhiyu()
