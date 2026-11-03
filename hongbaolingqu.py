"""红点奖励领取：进入任务面板，遍历各页签点掉所有可领取奖励，最后回到主界面。

覆盖：每日任务 / 公会任务 / 成长挑战 / 赛季任务（二级玩法页 + 底部三个阶段页）/
家园目标，以及主界面「赛季手册」的赛季里程碑一键领取。
不覆盖：翻翻乐（红点是「有钥匙没用」，需要反复点「点击增加进度」，属玩法不是领取）、
菜单「活动」页签（每个活动界面各异且随赛季轮换，需逐个适配）。
"""

import time

from common import (
    check_stop,
    click_blank_to_exit,
    click_position,
    find_center_silent,
    get_template_path,
    log,
    recover_to_main_interface,
    wait_and_click,
)

tpl_caidan = get_template_path("caidan.png")
tpl_renwu = get_template_path("renwu.png")
tpl_richangrenwu_tab = get_template_path("richangrenwutab.png")
tpl_gonghuirenwu = get_template_path("gonghuirenwu.png")
tpl_chengzhang = get_template_path("chengzhangtiaozhan.png")
tpl_saijirenwu = get_template_path("saijirenwu.png")
tpl_jiayuan = get_template_path("jiayuanmubiao.png")
tpl_wanfa = get_template_path("wanfa.png")
tpl_jieduaimubiao = get_template_path("jieduaimubiao.png")
tpl_saijichengzhang = get_template_path("saijichengzhangrenwu.png")
tpl_saijijieduan = get_template_path("saijijieduan.png")
tpl_yijianlingqu = get_template_path("yijianlingqu.png")
tpl_lingqu = get_template_path("lingqu.png")
tpl_blank_close = get_template_path("dianjikongbaichuguanbi.png")
tpl_saijishouchuo = get_template_path("saijishouchuo.png")
tpl_saijilichengbei = get_template_path("saijilichengbei.png")
# 任务面板底部页签栏（未选中态灰字）。面板会记住上次停留的页签，选中态会变绿
# （实测 fanfanle 选中后只剩 0.724 分），因此「面板已打开」用多页签或判断。
PANEL_TAB_TEMPLATES = (
    tpl_richangrenwu_tab,
    tpl_chengzhang,
    tpl_saijirenwu,
    tpl_jiayuan,
)

# 面板左下角返回箭头：实测任务面板/赛季手册用的是 exitck 这套外观，
# 玩法目录的 exit.png 与菜单的 fanhui.png 在这里都只有 0.42 分，匹配不到。
tpl_panel_back = get_template_path("exitck.png")

# 赛季任务的二级页签（玩法 / 活跃 / 限时 / 养成 / 剧情）等宽排列，
# 以「玩法」命中位置为基准横向偏移，避免为每个页签单独存一份模板。
SEASON_SUB_TAB_OFFSET_X = [0, 132, 264, 397, 532]

# 主界面「赛季手册」图标位于其文字标签左上方
SEASON_BOOK_ICON_OFFSET = (-7, -31)

# 单个界面最多点击多少次领取（防止领取后界面不刷新导致死循环）
MAX_CLAIM_PER_VIEW = 30

# 进入任务面板的重试次数
ENTRY_RETRY = 2


def _close_reward_popup():
    """领取后若弹出「获得奖励」，点空白关闭。"""
    if find_center_silent(tpl_blank_close, threshold=0.8, timeout=1.0):
        click_blank_to_exit()
        time.sleep(0.8)
        return True
    return False


def claim_current_view():
    """在当前界面反复点击「一键领取」与单个「领取」，直到两者都不再出现。

    先点一键领取：单个「领取」模板带勾选圆标，与一键领取按钮外观不同，
    两者互不误命中，因此顺序只影响次数，不影响正确性。
    """
    clicked = 0
    while clicked < MAX_CLAIM_PER_VIEW:
        check_stop()
        if wait_and_click(tpl_yijianlingqu, "yijianlingqu", 0.8, timeout=1.0):
            clicked += 1
            _close_reward_popup()
            continue

        pos = find_center_silent(tpl_lingqu, threshold=0.8, timeout=0.5)
        if not pos:
            break
        click_position(pos, wait=1.0, twice=False)
        clicked += 1
        _close_reward_popup()

    if clicked >= MAX_CLAIM_PER_VIEW:
        log(f"单个界面领取点击达到上限 {MAX_CLAIM_PER_VIEW} 次，跳过当前界面。")
    return clicked


def _panel_open():
    """底部页签栏里任意一个未选中页签可见，即认为任务面板已打开。"""
    return any(
        find_center_silent(template, threshold=0.8, timeout=1.0)
        for template in PANEL_TAB_TEMPLATES
    )


def _open_task_panel():
    """菜单 -> 任务，用底部页签栏确认面板已打开。

    重试时必须先判断是否已经停在菜单里：菜单打开后 HUD 上的 caidan 按钮就消失了，
    照着原样再点一次菜单只会白等一轮（实测第 2 次尝试因此两处都找不到）。
    """
    for attempt in range(1, ENTRY_RETRY + 1):
        check_stop()
        if not find_center_silent(tpl_renwu, threshold=0.8, timeout=1.0) and not wait_and_click(
            tpl_caidan, f"caidan({attempt})", 0.8, timeout=5.0
        ):
            log(f"第 {attempt} 次未找到菜单入口 caidan。")
            continue
        if not wait_and_click(tpl_renwu, f"renwu({attempt})", 0.8, timeout=5.0):
            log(f"第 {attempt} 次点击菜单后未找到任务入口 renwu。")
            continue
        if _panel_open():
            time.sleep(0.8)
            return True
        log(f"第 {attempt} 次点击任务后未确认进入任务面板（底部页签栏缺失）。")
    return False


def _sweep_view(name):
    count = claim_current_view()
    log(f"红点领取：{name} 领取 {count} 项。")
    return count


def _sweep_season_task_tab():
    """赛季任务：当前视图 + 二级玩法页 + 底部三个阶段页。"""
    total = _sweep_view("赛季任务")

    anchor = find_center_silent(tpl_wanfa, threshold=0.8, timeout=1.5)
    if anchor:
        for offset_x in SEASON_SUB_TAB_OFFSET_X:
            check_stop()
            click_position((anchor[0] + offset_x, anchor[1]), wait=1.0, twice=False)
            total += _sweep_view(f"赛季任务-二级页(偏移 {offset_x})")
    else:
        log("赛季任务未识别到「玩法」二级页签，跳过二级页遍历。")

    for template, stage_name in (
        (tpl_jieduaimubiao, "阶段目标"),
        (tpl_saijichengzhang, "赛季成长任务"),
        (tpl_saijijieduan, "赛季阶段"),
    ):
        check_stop()
        if not wait_and_click(template, f"赛季任务-{stage_name}", 0.8, timeout=2.0):
            log(f"未找到赛季任务底部页签「{stage_name}」，跳过。")
            continue
        total += _sweep_view(f"赛季任务-{stage_name}")
    return total


def _claim_task_panel():
    """任务面板各页签依次领取。返回领取总数。"""
    total = 0
    # 面板会停在上次浏览的页签，先显式点回每日任务，避免漏扫
    if wait_and_click(tpl_richangrenwu_tab, "richangrenwutab", 0.8, timeout=3.0):
        time.sleep(0.8)
    total += _sweep_view("每日任务")

    if wait_and_click(tpl_gonghuirenwu, "gonghuirenwu", 0.8, timeout=2.0):
        total += _sweep_view("公会任务")
    else:
        log("未找到公会任务页签，跳过。")

    for template, tab_name in (
        (tpl_chengzhang, "成长挑战"),
        (tpl_saijirenwu, "赛季任务"),
        (tpl_jiayuan, "家园目标"),
    ):
        check_stop()
        if not wait_and_click(template, f"页签 {tab_name}", 0.8, timeout=3.0):
            log(f"未找到任务面板页签「{tab_name}」，跳过。")
            continue
        if tab_name == "赛季任务":
            total += _sweep_season_task_tab()
        else:
            total += _sweep_view(tab_name)
    return total


def _claim_season_book(label_pos):
    """主界面「赛季手册」→ 赛季里程碑页的一键领取。label_pos 为文字标签中心。"""
    click_position(
        (label_pos[0] + SEASON_BOOK_ICON_OFFSET[0], label_pos[1] + SEASON_BOOK_ICON_OFFSET[1]),
        wait=1.5,
        twice=False,
    )
    if not find_center_silent(tpl_saijilichengbei, threshold=0.8, timeout=3.0):
        log("点击赛季手册后未确认进入赛季里程碑界面，跳过。")
        wait_and_click(tpl_panel_back, "exitck(赛季手册)", 0.8, timeout=2.0)
        return 0
    count = _sweep_view("赛季手册-赛季里程碑")
    wait_and_click(tpl_panel_back, "exitck(赛季手册)", 0.8, timeout=2.0)
    return count


def main():
    """执行红点奖励领取。返回 True=至少进入过其中一个领取界面，False=两处入口都不在。"""
    log("开始执行红点奖励领取...")
    total = 0
    entered = False

    if _open_task_panel():
        entered = True
        total += _claim_task_panel()
        wait_and_click(tpl_panel_back, "exitck(任务面板)", 0.8, timeout=3.0)
        time.sleep(1.0)
    else:
        log("未能进入任务面板，跳过任务面板领取。")

    check_stop()
    label = find_center_silent(tpl_saijishouchuo, threshold=0.8, timeout=1.5)
    if not label:
        # 面板领取可能停在菜单/子页里，HUD 上的赛季手册标签看不到；先回主界面再判一次
        recover_to_main_interface()
        label = find_center_silent(tpl_saijishouchuo, threshold=0.8, timeout=1.5)
    if label:
        entered = True
        total += _claim_season_book(label)
    else:
        log("主界面未找到「赛季手册」入口，跳过。")

    log(f"红点奖励领取结束，共领取 {total} 项。")
    return entered


if __name__ == "__main__":
    main()
