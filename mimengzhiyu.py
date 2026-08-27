import random
import time

from common import (
    click_blank_to_exit,
    find_center_silent,
    get_template_path,
    send_coord,
    try_auto_configure_lineup,
    wait_and_click,
)
from flow_enter import flow_return_main
from jiance import check_and_handle_libao


# 随机等待函数，2-3秒
def random_sleep():
    time.sleep(random.uniform(2.0, 3.0))

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
tpl_dianjikongbaichuguanbi = get_template_path("dianjikongbaichuguanbi.png")

# 一场战斗最长等待多久（秒）
MAX_BATTLE_TIME = 180

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

# 战斗结束后清理「点击空白处关闭」结算弹窗
def close_result_popups(timeout=10.0):
    """循环点击「点击空白处关闭」，直到弹窗消失（连续 2 秒不再出现则停止）。
    迷梦之域结算后常弹出奖励/分享界面，不关闭会卡在该界面导致后续流程失败。"""
    print("【迷梦之域】开始清理结算弹窗（点击空白处关闭）...")
    start = time.time()
    last_seen = time.time()
    while time.time() - start < timeout:
        pos = find_center_silent(tpl_dianjikongbaichuguanbi, 0.8)
        if pos:
            print("【迷梦之域】检测到「点击空白处关闭」，点击关闭")
            send_coord(pos[0], pos[1])
            last_seen = time.time()
            random_sleep()
        else:
            if time.time() - last_seen > 2.0:
                # 兜底：检测不到「点击空白处关闭」时，点击屏幕空白处尝试关闭残留弹窗
                click_blank_to_exit()
                break
            time.sleep(0.5)
    print("【迷梦之域】结算弹窗清理完成")


# 处理战斗界面逻辑
def handle_battle():
    """处理战斗界面：优先 tiaoguozhandou(跳过战斗)；否则点 zhandou 开战，
    开战后若中途出现 tiaoguozhandou 也点击以快进（首次无预跳过时可中途跳过）；
    战斗结束后清理结算弹窗，避免卡在「点击空白处关闭」界面。"""
    # 先检查是否存在 tiaoguozhandou（预跳过）
    pos_tiaoguozhandou = find_center_silent(tpl_tiaoguozhandou, threshold=0.8)
    if pos_tiaoguozhandou:
        print("【迷梦之域】检测到 tiaoguozhandou（跳过战斗），优先点击。")
        send_coord(pos_tiaoguozhandou[0], pos_tiaoguozhandou[1])
        random_sleep()
    else:
        # 检查是否存在 zhandou
        pos_zhandou = find_center_silent(tpl_zhandou, threshold=0.8)
        if pos_zhandou:
            print("【迷梦之域】未检测到预跳过，点击 zhandou 开始战斗（首次通常需要观战）。")
            send_coord(pos_zhandou[0], pos_zhandou[1])
            random_sleep()
            # 开战后轮询：若出现 tiaoguozhandou 则点击快进跳过（解决首次无预跳过的问题）
            for _ in range(15):
                if find_center_silent(tpl_pujingjieshu, 0.8):
                    break
                pos_mid = find_center_silent(tpl_tiaoguozhandou, 0.8)
                if pos_mid:
                    print("【迷梦之域】战斗中检测到 tiaoguozhandou，点击快进跳过。")
                    send_coord(pos_mid[0], pos_mid[1])
                    random_sleep()
                    break
                time.sleep(1.0)
        else:
            print("【迷梦之域】未检测到 zhandou 或 tiaoguozhandou，处理战斗界面失败。")
            return False

    # 等待战斗结束，点击 pujingjieshu，超时时间 120 秒
    if not wait_and_click(tpl_pujingjieshu, "pujingjieshu", 0.8, timeout=120):
        print("【迷梦之域】点击 pujingjieshu 失败，处理战斗界面失败。")
        return False
    random_sleep()

    # 清理结算弹窗（点击空白处关闭），避免卡在结算界面
    close_result_popups()
    return True

def flow_mimengzhiyu(challenge_count=None, auto_configure_lineup=False):
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
    if not wait_and_click(tpl_wanfamulu, "wanfamulu", 0.7, recover_threshold=20):
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
            # 清理结算弹窗并回到主界面，避免卡在结算/玩法界面
            close_result_popups()
            flow_return_main()
            print("迷梦之域流程结束。")
            return True

        # 3. 点击 tiaozhan 挑战
        # 可选：挑战前先尝试自动配置通关阵容（检测并点击 tongguanzhenrong / yijiancaiyong）
        if auto_configure_lineup:
            if try_auto_configure_lineup():
                print("【迷梦之域】已自动采用通关阵容。")
            else:
                print("【迷梦之域】未检测到通关阵容入口，跳过自动配置。")
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
            # 清理结算弹窗并回到主界面，避免卡在结算/玩法界面
            close_result_popups()
            flow_return_main()
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
