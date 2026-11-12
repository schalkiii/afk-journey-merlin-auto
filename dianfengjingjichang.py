"""巅峰竞技场：自动点「开始挑战 / 继续挑战」并观战到结算，直到次数用完或达到配置上限。

实测入口：主界面 → 玩法目录 → 第二行中间的「巅峰竞技场」卡片。
界面特征：底部绿色长条按钮（首次是「开始挑战」，打完后变「继续挑战」）；
右侧竖排只有 商店 / 排行榜 / 战斗记录 / 巅峰联赛 四个玩法标签。
右下角「每日结算奖励」点开是排名奖励明细表（201-500 档高亮），**没有领取按钮**，
奖励按排名自动发放，因此本模块不实现领奖，只负责挑战。
入场时可能压着「每日结算」大弹窗（遮罩下绿色长条仍能匹配到），需先关掉再操作。
战斗中有「跳过」按钮（实测坐标约客户区 (1090,712)），点了直接出结算；
失败页的关闭提示模板匹配不到，改点面板外左上空白关闭。
竞技场会记住上次浏览的右侧页签（商店/排行榜/战斗记录/巅峰联赛），重新进入可能落在子页：
看不到「继续挑战」时点左下返回箭头回到挑战主页（实测返回后按钮 0.92）。
"""

import time

from common import (
    capture_failure_context,
    check_stop,
    click_position,
    dismiss_popup_away_from,
    find_center_silent,
    game_client_region,
    get_template_path,
    is_loading_screen,
    log,
    open_wanfamulu,
    random_sleep,
    recover_to_main_interface,
    wait_and_click,
    wait_until_loaded,
)
from jiance import check_and_handle_libao

tpl_dianfeng = get_template_path("dianfengjingjichang.png")
tpl_jixutiaozhan = get_template_path("dianfengjixutiaozhan.png")
tpl_xuanzeduishou = get_template_path("dianfengxuanzeduishou.png")
tpl_tiaozhan = get_template_path("dianfengtiaozhan.png")
tpl_bianji = get_template_path("dianfengbianji.png")
tpl_zhandou = get_template_path("dianfengzhandou.png")
tpl_tiaoguo = get_template_path("tiaoguo.png")
tpl_fail = get_template_path("fail.png")
tpl_exitck = get_template_path("exitck.png")
tpl_meirijiesuan = get_template_path("dianfengmeirijiesuan.png")
tpl_catalog_title = get_template_path("wanfamulubiaoti.png")

# 「每日结算」大弹窗的关闭点：弹窗覆盖全屏且在左上方留有空白，实测点这里只关弹窗、
# 不会碰到任何按钮（遮罩下的绿色长条在 y≈846，距离足够远）。
SETTLEMENT_DISMISS_POS = (1300, 200)

# 选择对手界面里三张对手卡片的固定点位（客户区 1600×900，取最左侧/最弱的一张）
OPPONENT_CLIENT_POS = (672, 422)

# 一场战斗最长等待多久（秒）
MAX_BATTLE_TIME = 180
# 单次运行最多挑战几场（每场消耗一次挑战次数）
DEFAULT_CHALLENGE_COUNT = 3
MAX_CHALLENGE_COUNT = 10

# 跳过之后的轮询节奏：每轮等多久、连续多少轮「完全没进展」就提前放弃。
# 4 × 5 秒 = 20 秒；正常结算远短于这个量级，真卡住时也不该盲等 180 秒。
SKIP_SETTLE_POLL = 5.0
SKIP_STALL_LIMIT = 4


def _wait_for_any(templates, timeout, interval=0.5, quiet=False):
    """等待多张图中任意一张出现；返回 (template_path, pos)，超时返回 None。

    `quiet=True` 时超时不打日志：轮询循环每轮都会超时一次，逐条打出来会把日志刷成
    「放弃 fail / jixutiaozhan」的连续墙（2026-11-12 实测 36 条），掩盖真正的原因。
    """
    start = time.time()
    while True:
        for template_path, name in templates:
            pos = find_center_silent(template_path, 0.8)
            if pos:
                log(f"{name} 出现，坐标: {pos}")
                return template_path, pos
        if time.time() - start > timeout:
            if not quiet:
                names = " / ".join(name for _, name in templates)
                log(f"{names} 在 {timeout} 秒内未出现，放弃等待。")
            return None
        time.sleep(interval)


def _close_daily_settlement():
    """关闭入场时压在界面上的「每日结算」大弹窗，返回是否关掉。

    该弹窗没有「点击空白处关闭」提示（通用模板匹配不到），实测点左上方空白即可关闭；
    先确认标题模板命中再点，避免无弹窗时盲点界面。
    """
    if not find_center_silent(tpl_meirijiesuan, 0.8, timeout=1.0):
        return False
    x0, y0, _w, _h = game_client_region()
    click_position((x0 + SETTLEMENT_DISMISS_POS[0], y0 + SETTLEMENT_DISMISS_POS[1]),
                   wait=1.2, twice=False)
    log("关闭「每日结算」弹窗。")
    return True


def _wait_panel(timeout=15.0):
    """等待回到巅峰竞技场挑战界面（「继续挑战」按钮可见）。"""
    return find_center_silent(tpl_jixutiaozhan, 0.8, timeout=timeout)


def _back_to_challenge_view():
    """从右侧子页（商店/排行榜/战斗记录/巅峰联赛）退回挑战主页。

    2026-11-07 实测：竞技场会记住上次浏览的右侧页签，重新进入时直接落在该子页，
    「继续挑战」不可见；此时点左下返回箭头一次即可回到挑战主页（实测返回后按钮 0.92）。
    """
    pos = find_center_silent(get_template_path("fanhui.png"), 0.8, timeout=2.0)
    if pos is None:
        return False
    click_position(pos, wait=1.5, twice=False)
    return _wait_panel(5.0)


def _enter_dianfeng():
    """主界面 → 玩法目录 → 巅峰竞技场，并用「继续挑战」按钮确认进入。"""
    if not open_wanfamulu(threshold=0.7, timeout=8):
        log("未找到主界面「玩法目录」入口。")
        return False
    time.sleep(1.2)
    entered = False
    for attempt in range(1, 3):
        if not wait_and_click(tpl_dianfeng, "dianfengjingjichang", 0.8, timeout=6):
            log("玩法目录里未找到「巅峰竞技场」卡片。")
            return False
        if _wait_panel(10.0):
            entered = True
            break
        if find_center_silent(tpl_catalog_title, 0.8, timeout=0):
            log(f"点击「巅峰竞技场」后目录仍在（第 {attempt} 次被吞），补点一次。")
            continue
        # 已离开目录但看不到挑战按钮：多半落在上次浏览的右侧子页，点返回回到挑战主页。
        if _back_to_challenge_view():
            entered = True
            break
        log("巅峰竞技场落在未知页面，无法回到挑战主页。")
        recover_to_main_interface()
        return False
    if not entered:
        log("多次点击后仍未进入巅峰竞技场挑战界面，结束。")
        recover_to_main_interface()
        return False
    # 入场时可能压着「每日结算」大弹窗：遮罩下绿色长条照样能匹配到，
    # 但后续选择对手的点位会被遮罩吞掉，所以先关弹窗再确认一次挑战界面。
    _close_daily_settlement()
    if not _wait_panel(5.0):
        log("关闭「每日结算」后仍未看到挑战按钮，判定没进入。")
        recover_to_main_interface()
        return False
    time.sleep(0.8)
    return True


def _select_opponent_and_lineup():
    """选择对手 → 三队确认 → 战斗。返回是否成功开战。

    实测流程：继续挑战后进入「选择对手」三张卡片，点最左（最弱）一张 →
    「挑战他!」→ 阵容界面默认队长第 1 队，底部按钮是「编辑下一场」，
    连点两次切到第 3 队后按钮才变成「战斗」。
    阵容页加载较慢：实测「编辑下一场」在点完挑战他后要 2~3 秒才出现，
    偶发超过 3 秒，所以这里给 6 秒窗口。
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

    # 依次编辑第 2、3 队；按钮变成「战斗」即停止。切换动画期间两种按钮都可能短暂
    # 不可见，必须「等任一种出现」：2026-11-07 实机先查战斗、再等编辑下一场，结果
    # 战斗还没渲染出来就去等已消失的编辑按钮，白等 6 秒后误判失败（完成 0 场）。
    for _ in range(3):
        hit = _wait_for_any(
            [(tpl_zhandou, "战斗"), (tpl_bianji, "编辑下一场")], timeout=6.0
        )
        if hit is None:
            log("阵容页既没有「战斗」也没有「编辑下一场」，结束。")
            return False
        hit_tpl, hit_pos = hit
        click_position(hit_pos, wait=1.5, twice=False)
        if hit_tpl == tpl_zhandou:
            return True
        time.sleep(0.8)
    log("三队确认后仍未出现「战斗」按钮，结束。")
    return False


def _settle_after_skip(skip_pos):
    """点过「跳过」之后等结算信号；返回 (template_path, pos) 或 None。

    2026-11-12 实机（今天唯一的「卡住」现场）：第 2 场 08:50:21 点了「跳过」，
    之后界面既没有失败页、也没有「继续挑战」，也没有「点击空白处关闭」——旧实现
    只在那个提示模板命中时才肯动作，于是整整空转 180 秒（36 轮「放弃 fail /
    jixutiaozhan」）才放弃，用户看到的就是「显示完成但中途卡住」。

    现在每一轮都做三件事，而不是干等：
    1. 「跳过」按钮还在 → 上一击被吞、战斗仍在进行，按原位置补点一次；
    2. 命中任一已知弹窗/提示（点击空白处关闭、每日结算、加载中）→ 关掉或等加载；
    3. 连续 SKIP_STALL_LIMIT 轮完全没有可识别元素、也没有任何补救动作可做 →
       立刻保存失败现场并放弃，而不是把 180 秒耗光。
    """
    deadline = time.time() + MAX_BATTLE_TIME
    stall = 0
    while time.time() < deadline:
        check_stop()
        outcome = _wait_for_any(
            [(tpl_fail, "fail"), (tpl_jixutiaozhan, "jixutiaozhan")],
            timeout=SKIP_SETTLE_POLL,
            quiet=True,
        )
        if outcome is not None:
            return outcome

        # ① 战斗其实还在进行：跳过没生效，补点（跳过一次失败是常态，见实机记录）
        if find_center_silent(tpl_tiaoguo, 0.8, timeout=0):
            log("「跳过」后战斗仍在进行，补点一次跳过")
            click_position(skip_pos, wait=1.2, twice=False)
            stall = 0
            continue

        # ② 各类已知提示/弹窗：关掉后立刻重判
        if find_center_silent(get_template_path("dianjikongbaichuguanbi.png"), 0.8, timeout=0):
            dismiss_popup_away_from()
            log("关闭战斗结算弹窗后继续等待结束信号。")
            stall = 0
            continue
        if find_center_silent(tpl_meirijiesuan, 0.8, timeout=0):
            _close_daily_settlement()
            stall = 0
            continue
        if is_loading_screen():
            log("「跳过」后进入加载画面，等待加载结束")
            wait_until_loaded(15.0)
            stall = 0
            continue

        # ③ 完全认不出的界面：数到上限就留现场退出，绝不无限空转
        stall += 1
        log(f"「跳过」后界面无可识别信号（第 {stall}/{SKIP_STALL_LIMIT} 轮），继续观察")
        if stall >= SKIP_STALL_LIMIT:
            capture_failure_context("巅峰竞技场", "跳过之后无法识别结算界面")
            log("跳过之后始终无法识别界面，保存现场后结束本场")
            return None
    log(f"跳过之后 {MAX_BATTLE_TIME} 秒内未出现结算信号，结束。")
    return None


def _fight_once(index):
    """挑战一场：继续挑战 → 选对手 → 三队确认 → 战斗 → 等结算，返回是否打完一场。"""
    # 「继续挑战」点击可能被窗口激活吞掉（2026-11-08 实机第 2 场）：没进选对手界面
    # 就补点一次，两次都不进才判定次数用尽。
    entered_select = False
    for attempt in range(1, 3):
        if not wait_and_click(tpl_jixutiaozhan, f"继续挑战({index})", 0.8, timeout=10):
            if attempt == 1:
                continue
            log(f"第 {index} 次没有找到「继续挑战」按钮，结束。")
            return False
        random_sleep()
        if find_center_silent(tpl_xuanzeduishou, 0.8, timeout=8.0) is not None:
            entered_select = True
            break
        # 防误补点：选择对手页的「挑战他」按钮已可见时，说明其实已进入（2026-11-08 实机：
        # 标题模板 3 秒内没等到就误判被吞、补点反而把界面点回去）
        if find_center_silent(tpl_tiaozhan, 0.8, timeout=0) is not None:
            entered_select = True
            break
        log(f"点击「继续挑战({index})」后未进入选择对手，补点一次。")
    if not entered_select:
        log(f"第 {index} 场未能进入选择对手界面，结束。")
        return False

    if not _select_opponent_and_lineup():
        return False
    random_sleep()

    # 战斗中有「跳过」按钮（实测点它直接出结算）；结束时可能停在失败页，
    # 也可能直接回到挑战界面。三种信号谁先出现就按谁走。
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
        outcome = _settle_after_skip(outcome_pos)
        if outcome is None:
            return False
        outcome_tpl, outcome_pos = outcome

    if outcome_tpl == tpl_fail:
        # 失败页的「点击空白处关闭」提示模板在这里只有 0.41 分（实测），通用关弹窗无效；
        # 直接点面板外的左上方空白，该点位在失败页与「每日结算」页都避开所有按钮。
        x0, y0, _w, _h = game_client_region()
        click_position((x0 + SETTLEMENT_DISMISS_POS[0], y0 + SETTLEMENT_DISMISS_POS[1]),
                       wait=1.5, twice=False)
        if not _wait_panel(15.0):
            # 首次点击可能被吞（2026-11-08 实跑：失败页关不掉导致第 2 场后整轮提前结束、
            # 挑战次数有残留）：补点一次空白，仍不行再走「回到挑战主页」兜底。
            click_position((x0 + SETTLEMENT_DISMISS_POS[0], y0 + SETTLEMENT_DISMISS_POS[1]),
                           wait=1.5, twice=False)
            if not _wait_panel(10.0) and not _back_to_challenge_view():
                log("关闭失败页后未回到挑战界面，结束。")
                return False
    else:
        # 胜利会直接回到挑战界面；清掉可能残留的奖励/段位变化弹窗
        dismiss_popup_away_from()
    return True


def flow_dianfeng(challenge_count=DEFAULT_CHALLENGE_COUNT):
    """巅峰竞技场主流程。返回 True=正常进入并执行（含休赛期跳过），False=没进入。"""
    log("开始执行巅峰竞技场...")
    recover_to_main_interface()
    if not _enter_dianfeng():
        # 2026-11-09 实机：巅峰竞技场进入休赛期后点卡片只回到家园、看不到「继续挑战」，
        # 旧实现记任务失败。拿不到挑战按钮说明当日无赛程（休赛期/未开赛），按跳过处理。
        log("巅峰竞技场入口不可用（休赛期或未开赛），本日跳过")
        recover_to_main_interface()
        return True

    times = max(1, min(int(challenge_count), MAX_CHALLENGE_COUNT))
    done = 0
    for index in range(1, times + 1):
        if not _fight_once(index):
            # 单场失败不等于次数用尽（2026-11-08：第 2 场失败页卡住导致第 3 场没打）：
            # 先回到挑战主页，「继续挑战」仍在就继续下一场；按钮消失才是真的打完。
            _back_to_challenge_view()
            if find_center_silent(tpl_jixutiaozhan, 0.8, timeout=3.0):
                log(f"第 {index} 场未完成，但「继续挑战」仍在，继续下一场。")
                continue
            break
        done += 1
    log(f"巅峰竞技场：完成 {done} 场（上限 {times} 次）。")

    wait_and_click(tpl_exitck, "exitck(巅峰竞技场)", 0.8, timeout=3.0)
    recover_to_main_interface()
    check_and_handle_libao()
    return True
