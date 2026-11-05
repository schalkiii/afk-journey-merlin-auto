"""巅峰竞技场：自动点「继续挑战」并跳过战斗，直到次数用完或达到配置上限。

实测入口：主界面 → 玩法目录 → 第二行中间的「巅峰竞技场」卡片。
界面特征：底部绿色「继续挑战」长条按钮；右侧竖排有「挑战奖励」「每日结算奖励」，
但奖励领取入口尚未实机验证，本模块只负责挑战，避免盲点误触其它按钮。
战斗流程与普竞一致：继续挑战 → 战斗 → 跳过 → 回到挑战界面。
"""

import time

from common import (
    BOTTOM_BAR_CLIENT_REGION,
    click_position,
    dismiss_popup_away_from,
    find_center_silent,
    game_client_region,
    get_template_path,
    log,
    random_sleep,
    recover_to_main_interface,
    wait_and_click,
)
from jiance import check_and_handle_libao

tpl_wanfamulu = get_template_path("wanfamulu.png")
tpl_dianfeng = get_template_path("dianfengjingjichang.png")
tpl_jixutiaozhan = get_template_path("dianfengjixutiaozhan.png")
tpl_xuanzeduishou = get_template_path("dianfengxuanzeduishou.png")
tpl_tiaozhan = get_template_path("dianfengtiaozhan.png")
tpl_bianji = get_template_path("dianfengbianji.png")
tpl_zhandou = get_template_path("dianfengzhandou.png")
tpl_tiaoguo = get_template_path("tiaoguo.png")
tpl_fail = get_template_path("fail.png")
tpl_exitck = get_template_path("exitck.png")

# 选择对手界面里三张对手卡片的固定点位（客户区 1600×900，取最左侧/最弱的一张）
OPPONENT_CLIENT_POS = (672, 422)

# 一场战斗最长等待多久（秒）
MAX_BATTLE_TIME = 180
# 单次运行最多挑战几场（每场消耗一次挑战次数）
DEFAULT_CHALLENGE_COUNT = 3
MAX_CHALLENGE_COUNT = 10


def _wait_for_any(templates, timeout, interval=0.5):
    """等待多张图中任意一张出现；返回 (template_path, pos)，超时返回 None。"""
    start = time.time()
    while True:
        for template_path, name in templates:
            pos = find_center_silent(template_path, 0.8)
            if pos:
                print(f"{name} 出现，坐标: {pos}")
                return template_path, pos
        if time.time() - start > timeout:
            names = " / ".join(name for _, name in templates)
            print(f"{names} 在 {timeout} 秒内未出现，放弃等待。")
            return None
        time.sleep(interval)


def _wait_panel(timeout=15.0):
    """等待回到巅峰竞技场挑战界面（「继续挑战」按钮可见）。"""
    return find_center_silent(tpl_jixutiaozhan, 0.8, timeout=timeout)


def _enter_dianfeng():
    """主界面 → 玩法目录 → 巅峰竞技场，并用「继续挑战」按钮确认进入。"""
    if not wait_and_click(tpl_wanfamulu, "wanfamulu", 0.7,
                          client_region=BOTTOM_BAR_CLIENT_REGION, timeout=8):
        log("未找到主界面「玩法目录」入口。")
        return False
    time.sleep(1.2)
    if not wait_and_click(tpl_dianfeng, "dianfengjingjichang", 0.8, timeout=8):
        log("玩法目录里未找到「巅峰竞技场」卡片。")
        return False
    if not _wait_panel(15.0):
        log("点击巅峰竞技场后未看到「继续挑战」按钮，判定没进入。")
        recover_to_main_interface()
        return False
    time.sleep(0.8)
    return True


def _select_opponent_and_lineup():
    """选择对手 → 三队确认 → 战斗。返回是否成功开战。

    实测流程：继续挑战后进入「选择对手」三张卡片，点最左（最弱）一张 →
    「挑战他!」→ 阵容界面默认队长第 1 队，底部按钮是「编辑下一场」，
    连点两次切到第 3 队后按钮才变成「战斗」。
    """
    if not find_center_silent(tpl_xuanzeduishou, 0.8, timeout=10.0):
        log("未进入选择对手界面，结束。")
        return False

    x0, y0, _w, _h = game_client_region()
    click_position((x0 + OPPONENT_CLIENT_POS[0], y0 + OPPONENT_CLIENT_POS[1]),
                   wait=1.5, twice=False)
    if not wait_and_click(tpl_tiaozhan, "挑战他", 0.8, timeout=5.0):
        log("选完对手后没有出现「挑战他」按钮，结束。")
        return False

    # 依次编辑第 2、3 队；按钮变成「战斗」即停止
    for _ in range(3):
        if find_center_silent(tpl_zhandou, 0.8, timeout=1.0):
            break
        if not wait_and_click(tpl_bianji, "编辑下一场", 0.8, timeout=3.0):
            log("未找到「编辑下一场」按钮，结束。")
            return False
        time.sleep(0.8)
    if not wait_and_click(tpl_zhandou, "战斗", 0.8, timeout=5.0):
        log("三队确认后没有出现「战斗」按钮，结束。")
        return False
    return True


def _fight_once(index):
    """挑战一场：继续挑战 → 选对手 → 三队确认 → 战斗 → 等结算，返回是否打完一场。"""
    if not wait_and_click(tpl_jixutiaozhan, f"继续挑战({index})", 0.8, timeout=10):
        log(f"第 {index} 次没有找到「继续挑战」按钮，结束。")
        return False
    random_sleep()

    if not _select_opponent_and_lineup():
        return False
    random_sleep()

    # 巅峰竞技场没有「跳过」：整场观战，结束时直接出结算（胜利回到挑战界面，
    # 失败停在「战斗失败」页）。三种信号谁先出现就按谁走。
    outcome = _wait_for_any(
        [(tpl_tiaoguo, "tiaoguo"), (tpl_fail, "fail"), (tpl_jixutiaozhan, "jixutiaozhan")],
        timeout=MAX_BATTLE_TIME,
    )
    if outcome is None:
        log("战斗结束信号未出现，结束。")
        return False
    outcome_tpl, outcome_pos = outcome
    if outcome_tpl == tpl_tiaoguo:
        click_position(outcome_pos, wait=1.2, twice=False)
        outcome = _wait_for_any(
            [(tpl_fail, "fail"), (tpl_jixutiaozhan, "jixutiaozhan")],
            timeout=MAX_BATTLE_TIME,
        )
        if outcome is None:
            log("跳过之后未出现结算信号，结束。")
            return False
        outcome_tpl, outcome_pos = outcome

    if outcome_tpl == tpl_fail:
        # 「点击空白处关闭」的小模板在失败页上实测匹配不到，直接用通用关弹窗
        # （它点的是提示文字左上方空白，不会误触按钮），再等挑战界面回来。
        dismiss_popup_away_from()
        if not _wait_panel(15.0):
            log("关闭失败页后未回到挑战界面，结束。")
            return False
    else:
        # 胜利会直接回到挑战界面；清掉可能残留的奖励/段位变化弹窗
        dismiss_popup_away_from()
    return True


def flow_dianfeng(challenge_count=DEFAULT_CHALLENGE_COUNT):
    """巅峰竞技场主流程。返回 True=正常进入并执行，False=没进入。"""
    log("开始执行巅峰竞技场...")
    recover_to_main_interface()
    if not _enter_dianfeng():
        return False

    times = max(1, min(int(challenge_count), MAX_CHALLENGE_COUNT))
    done = 0
    for index in range(1, times + 1):
        if not _fight_once(index):
            break
        done += 1
    log(f"巅峰竞技场：完成 {done} 场（上限 {times} 次）。")

    wait_and_click(tpl_exitck, "exitck(巅峰竞技场)", 0.8, timeout=3.0)
    recover_to_main_interface()
    check_and_handle_libao()
    return True
