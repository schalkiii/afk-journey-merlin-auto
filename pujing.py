"""普通竞技场流程：连打至付费门票、战斗 / 结算状态机与次数收敛。

关键接口 `execute_battle_flow()` 与 `flow_pujing()`；依赖 `common` 的模板匹配
与「跳过 / 结算谁先出现就按谁走」的等待原语。
"""

import time

from common import (
    display_name,
    find_center_silent,
    get_template_path,
    open_wanfamulu,
    random_sleep,
    send_coord,
    wait_and_click,
)
from jiance import check_and_handle_libao

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
                print(f"{display_name(name)} 出现，第 {attempt} 次检测，坐标: {pos}")
                return template_path, name, pos

        elapsed = time.time() - start
        if elapsed > timeout:
            names = " / ".join([display_name(n) for _, n in templates])
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
    
    print(f"找到最左边且最下面的战斗按钮: {display_name(name)}, 坐标: {pos}")
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
    if not open_wanfamulu(threshold=0.7, timeout=8):
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
            print("未找到挑战按钮，按次数用尽结束。")
            return True

        hit_tpl, hit_name, hit_pos = hit
        print(f"点击 {display_name(hit_name)}")
        send_coord(hit_pos[0], hit_pos[1])
        random_sleep()

        # 4. 判断是开始挑战还是继续挑战
        if hit_tpl == tpl_pujingjixutiaozhan:
            # 继续挑战，直接跳过门票检测，选择战斗按钮并执行战斗
            print("识别到继续挑战，跳过门票检测，直接进入战斗流程。")
            time.sleep(1.0)
            battle_hit = find_leftmost([tpl_pujingzhandou, tpl_zhandou], threshold=0.8)
            if battle_hit is None:
                return _finish_without_battle()
            battle_tpl, battle_name, battle_pos = battle_hit
            if not _battle_then_continue(battle_tpl, battle_name, battle_pos):
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
                return _finish_without_battle()
            battle_tpl, battle_name, battle_pos = battle_hit
            if not _battle_then_continue(battle_tpl, battle_name, battle_pos):
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
                print(f"点击 {display_name(hit_name)}")
                send_coord(hit_pos[0], hit_pos[1])
                random_sleep()

                # 选择战斗按钮并执行战斗
                time.sleep(1.0)
                battle_hit = find_leftmost([tpl_pujingzhandou, tpl_zhandou], threshold=0.8)
                if battle_hit is None:
                    return _finish_without_battle()
                battle_tpl, battle_name, battle_pos = battle_hit
                if not _battle_then_continue(battle_tpl, battle_name, battle_pos):
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


def _finish_without_battle():
    """点完「开始挑战」却找不到战斗按钮：分清「次数用尽」和真异常。

    2026-11-14 实跑：连打 5 场全胜（08:03:28~08:05:11 五次结算），第 6 次点
    「开始挑战」后界面既没有战斗按钮、也没有免费门票提示（付费门票那张图不在这一屏），
    旧实现走到 `return False`，整条任务被记成失败——次数打完是正常结果，不是故障。
    判据按可靠性排序：门票提示 → 挑战入口仍在 → 都认不出才判失败。
    """
    if (find_center_silent(tpl_mianfeimenpiao, 0.8, timeout=2.0)
            or find_center_silent(tpl_fufeimenpiao, 0.8, timeout=0)):
        print("出现门票提示，竞技场次数已用尽，普竞正常结束。")
        return True
    if (find_center_silent(tpl_kaishitiaozhan, 0.8, timeout=2.0)
            or find_center_silent(tpl_pujingjixutiaozhan, 0.8, timeout=0)):
        print("找不到战斗按钮但挑战入口仍在，判定次数已用尽，普竞正常结束。")
        return True
    print("未找到战斗按钮，且认不出当前界面，普竞流程结束。")
    return False


def _battle_then_continue(battle_tpl, battle_name, battle_pos):
    """打一场普竞；单场失败但挑战按钮仍在时返回 True（继续下一场）。

    2026-11-08 实跑：第 2 场点战斗被吞后 execute_battle_flow 返回 False，
    整轮直接结束、竞技场次数有残留。单场失败不等于次数用尽，挑战按钮还在就继续。
    """
    if execute_battle_flow(battle_tpl, battle_name, battle_pos):
        return True
    if (find_center_silent(tpl_kaishitiaozhan, 0.8, timeout=3)
            or find_center_silent(tpl_pujingjixutiaozhan, 0.8, timeout=0)):
        print("本场未完成，但挑战按钮仍在，继续下一场。")
        return True
    return False


def execute_battle_flow(battle_tpl, battle_name, battle_pos):
    """执行战斗流程"""
    print(f"点击 {battle_name}")
    send_coord(battle_pos[0], battle_pos[1])
    random_sleep()

    # 点击 zhandou 进入战斗；点击可能被窗口激活吞掉（2026-11-08 实跑第 2 场 15 秒未出现），
    # 未出现且战斗按钮仍在时补点一次；按钮已消失说明界面已切换，不再盲点。
    zhandou_clicked = False
    for attempt in range(1, 3):
        if wait_and_click(tpl_zhandou, f"zhandou({attempt})", 0.8, timeout=15):
            zhandou_clicked = True
            break
        if find_center_silent(battle_tpl, 0.8) is None:
            print("战斗按钮已消失，界面可能已切换，不再补点。")
            break
        print("zhandou 未出现且战斗按钮仍在，补点一次。")
        send_coord(battle_pos[0], battle_pos[1])
        random_sleep()
    if not zhandou_clicked:
        # 2026-11-09 实机：连续 30 秒等不到「战斗」→ 整条任务失败。此时往往是次数用尽、
        # 界面弹出门票提示；识别到门票就按「正常结束」处理，不再误报失败。
        if (find_center_silent(tpl_mianfeimenpiao, 0.8, timeout=2.0)
                or find_center_silent(tpl_fufeimenpiao, 0.8, timeout=0)):
            print("出现门票提示，竞技场次数已用尽，本场正常结束。")
            return True
        print("点击 zhandou 失败，本场结束。")
        return False
    random_sleep()

    # 战斗开始后会先出现「跳过」，也可能因战斗自动结束/加载较慢而直接出结算。
    # 旧实现只等 tiaoguo 15 秒，等不到就中止整轮（实测打到第 3 场停在 2/5 次），
    # 这里改为「跳过 / 结算谁先出现就按谁走」，并把等待上限放宽到整场战斗时长。
    outcome = wait_for_any(
        [(tpl_tiaoguo, "tiaoguo"), (tpl_pujingjieshu, "pujingjieshu")],
        threshold=0.8,
        timeout=MAX_BATTLE_TIME,
        interval=0.5,
    )
    if outcome is None:
        print("跳过/结算都未出现，普晶流程结束。")
        return False
    outcome_tpl, _outcome_name, outcome_pos = outcome
    if outcome_tpl == tpl_tiaoguo:
        send_coord(outcome_pos[0], outcome_pos[1])
        random_sleep()
        pos = wait_for_appearance(tpl_pujingjieshu, "pujingjieshu", 0.8)
    else:
        pos = outcome_pos
    if pos is None:
        print("未识别到 pujingjieshu，普晶流程结束。")
        return False
    print("识别到 pujingjieshu，等待3秒后点击...")
    time.sleep(3.0)
    send_coord(pos[0], pos[1])
    random_sleep()

    # 结算点击可能被窗口激活/动画吞掉：最多补点两次，并确认真的回到挑战界面。
    # 找不到挑战按钮但已经不在结算页时，往往只是次数用尽，交给主循环按正常结束处理。
    for attempt in range(1, 3):
        if find_center_silent(tpl_kaishitiaozhan, 0.8, timeout=8) or \
                find_center_silent(tpl_pujingjixutiaozhan, 0.8, timeout=0):
            return True
        if find_center_silent(tpl_pujingjieshu, 0.8, timeout=0):
            print(f"结算页仍在，补点 pujingjieshu（第 {attempt} 次）。")
            send_coord(pos[0], pos[1])
            random_sleep()
        else:
            # 可能弹了段位/奖励弹窗，先清掉再看
            check_and_handle_libao()
            random_sleep()
    return True

if __name__ == "__main__":
    flow_pujing()
