# D:\workspace\afk-journey-merlin-auto\jieshezhanxian.py
"""结社战线每日流程：挑战到打不动为止，再把当日剩余扫荡次数一次扫完。

流程（自主界面起）：
1. flow_enter_guild_play 经「玩法目录 → 公会玩法 → 结社战线」卡片进入结社战线主界面；
2. 挑战循环：点「挑战」进备战界面 → 点「战斗」开打 → 结算出现「继续挑战」即为胜利，
   点它会直接回到下一层的备战界面继续打；等不到「继续挑战」就判定本场未取胜，退出循环；
3. 扫荡：点主界面「扫荡」进「扫荡关卡」面板 → 点「最大」档一次选满 → 点「扫荡」→
   关闭「扫荡完成」结算 → 返回主界面；面板打不开即当日扫荡次数已用尽；
4. 清理退出时弹出的礼包广告，并兜底回主界面。

设计要点：
- 挑战与扫荡是两条独立计数（实测：打赢一场后主界面「今日剩余」仍为 4），所以「赢了继续
  挑战、输了才扫荡」不会互相挤占额度，也不需要为扫荡预留挑战次数。
- 结社战线战斗没有「跳过战斗」入口（实测整场只能观战），故结算等待上限给到 180 秒。
- 胜利结算的「继续挑战」与失败结算的「再次挑战」只差首字、按钮样式相同（实测互相能匹配到
  0.782），故「继续挑战」用 0.85 阈值，并同时轮询失败结算标题（jiesheshibai）——
  认出失败就立刻结束挑战，不必等 180 秒超时。
- 「扫荡完成」结算的「点击空白处关闭」热区（屏幕底部居中）与面板的「扫荡」按钮几乎重合
  （y 仅差 15 像素），在热区中心点击会在关掉结算的同时再触发一次扫荡；故统一改用
  common.dismiss_popup_away_from 点热区左上方的空白处。
- 面板内的「扫荡」按钮与主界面的「扫荡」按钮都是绿底白字，主界面模板在面板上也能匹配到
  0.94，故面板按钮用 0.95 的高阈值，避免在两个界面间串味。
- 从结社战线退出会弹「专属装备礼包」广告（实测必弹），用 jiance.check_and_handle_libao 清掉。

入口 main() 由 GUI「结社战线」脚本调用（每天一次，是否执行由用户在列表勾选）。
"""

import time

from common import (
    check_stop,
    click_position,
    dismiss_popup_away_from,
    find_center_silent,
    get_template_path,
    log,
    wait_until_loaded,
)
from flow_enter import flow_return_main
from flow_gonghui import flow_enter_guild_play
from jiance import check_and_handle_libao

# 模板路径
tpl_card = get_template_path("jieshezhanxian.png")              # 公会玩法页的入口卡片
tpl_title = get_template_path("jieshezhanxianbiaoti.png")       # 结社战线主界面标题
tpl_tiaozhan = get_template_path("jieshetiaozhan.png")          # 主界面「挑战」
tpl_saodang = get_template_path("jieshesaodang.png")            # 主界面「扫荡」
tpl_panel = get_template_path("jieshesaodangguanqia.png")       # 「扫荡关卡」面板标题
tpl_saodang_max = get_template_path("jieshesaodangmax.png")     # 扫荡次数「最大」档
tpl_saodang_btn = get_template_path("jieshesaodangbtn.png")     # 面板内「扫荡」
tpl_saodang_done = get_template_path("jieshesaodangwancheng.png")  # 「扫荡完成」结算
tpl_continue = get_template_path("jieshejixutiaozhan.png")      # 胜利结算的「继续挑战」
tpl_defeat = get_template_path("jiesheshibai.png")              # 「战斗失败」结算标题
tpl_battle = get_template_path("zhandou.png")                   # 备战界面「战斗」（通用模板）
tpl_back = get_template_path("exit.png")                        # 返回箭头（通用模板）

MATCH_THRESHOLD = 0.8
CONTINUE_THRESHOLD = 0.85  # 失败结算的「再次挑战」与「继续挑战」只差首字，实测相似 0.782，取高阈值隔开
SAODANG_BTN_THRESHOLD = 0.95   # 见模块文档：避免与主界面「扫荡」互相误命中
SETTLE_DELAY = 2.0             # 界面切换后的稳定等待
BATTLE_TIMEOUT = 180           # 一场战斗（含结算动画）的等待上限
PANEL_TIMEOUT = 10             # 备战界面 / 扫荡面板的加载等待上限
MAX_CHALLENGES = 20            # 单次任务最多挑战场次，防止连胜不停机
MAX_BACK_CLICKS = 4            # 逐层返回主界面的最多点击次数


def _find(template, threshold=MATCH_THRESHOLD, timeout=0):
    return find_center_silent(template, threshold, timeout=timeout)


def _wait_any(candidates, timeout):
    """轮询等待任意一个模板出现，candidates 为 (模板, 阈值) 列表；返回 (模板, 坐标)。

    超时返回 (None, None)。战斗结算的「继续挑战」与「再次挑战」只差首字，需要各自的阈值，
    故阈值随模板一起传入而不是统一取 MATCH_THRESHOLD。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        check_stop()
        for template, threshold in candidates:
            pos = _find(template, threshold)
            if pos is not None:
                return template, pos
        time.sleep(0.5)
    return None, None


def _click_and_expect(click_template, expect_template, expect_timeout=3,
                      attempts=3, wait=SETTLE_DELAY):
    """点击目标直到期望界面出现；首次点击可能被窗口激活吞掉，故最多重试 attempts 次。"""
    for _ in range(attempts):
        check_stop()
        pos = _find(click_template)
        if pos is None:
            return False
        click_position(pos, wait, twice=False)
        if _find(expect_template, timeout=expect_timeout) is not None:
            return True
    return False


def _back_to_main():
    """逐层点返回箭头，直到回到结社战线主界面（标题与「扫荡」同时可见）。"""
    for _ in range(MAX_BACK_CLICKS):
        if _find(tpl_title) is not None and _find(tpl_saodang) is not None:
            return True
        if _find(tpl_saodang_done) is not None or _find(tpl_continue) is not None:
            dismiss_popup_away_from()
            continue
        if not click_position(_find(tpl_back), SETTLE_DELAY):
            break
    return _find(tpl_title) is not None


def _challenge_until_lose():
    """挑战循环：胜利就继续挑战下一层，未取胜即结束。返回胜场数。"""
    if not _click_and_expect(tpl_tiaozhan, tpl_battle, expect_timeout=PANEL_TIMEOUT):
        log("【结社战线】未能进入备战界面，跳过挑战")
        return 0

    wins = 0
    for _ in range(MAX_CHALLENGES):
        check_stop()
        click_position(_find(tpl_battle), 1.0, twice=False)
        hit, pos = _wait_any(
            [(tpl_continue, CONTINUE_THRESHOLD),
             (tpl_defeat, MATCH_THRESHOLD),
             (tpl_title, MATCH_THRESHOLD)],
            BATTLE_TIMEOUT,
        )
        if hit is not tpl_continue:
            reason = "本场失败" if hit is tpl_defeat else "未识别到结算界面"
            log(f"【结社战线】{reason}，结束挑战（累计胜 {wins} 场）")
            break
        wins += 1
        log(f"【结社战线】第 {wins} 场胜利，继续挑战下一层")
        click_position(pos, SETTLE_DELAY, twice=False)
        if _find(tpl_battle, timeout=PANEL_TIMEOUT) is None:
            log("【结社战线】点「继续挑战」后未回到备战界面，停止挑战")
            break

    # 2026-11-09 实机：旧实现在挑战结束后立刻 _back_to_main()，把结社页面关掉，
    # 随后 _sweep_remaining 在主界面找不到「扫荡」按钮 → 误判「次数已用尽」，
    # 用户实际还有次数却没扫。挑战结束应留在结社页面，由 _sweep_remaining 自己回主页。
    return wins


def _back_to_guild_home():
    """回退到结社战线主页（有「扫荡」按钮的页面）；退不出来返回 False。

    2026-11-09 实机：挑战失败后停在失败结算页，直接找「扫荡」必然找不到，
    旧实现就把「扫荡面板未打开」当成「次数已用尽」，用户实际还有次数却没扫。
    """
    if find_center_silent(tpl_saodang, 0.8, timeout=2.0) is not None:
        return True
    for _ in range(3):
        check_stop()
        pos = find_center_silent(tpl_back, 0.8, timeout=2.0)
        if pos is None:
            # 失败结算页可能只有「点击空白处关闭」/「再次挑战」，先清弹窗再找返回
            dismiss_popup_away_from()
        else:
            click_position(pos, SETTLE_DELAY, twice=False)
        wait_until_loaded(8.0)
        if find_center_silent(tpl_saodang, 0.8, timeout=4.0) is not None:
            return True
    return False


def _sweep_remaining():
    """把当日剩余扫荡次数一次扫完；回不到主页/面板确实打不开才算无剩余次数。"""
    if not _back_to_guild_home():
        log("【结社战线】未回到结社战线主页，无法确认扫荡次数")
        return False

    if not _click_and_expect(tpl_saodang, tpl_panel, expect_timeout=PANEL_TIMEOUT):
        log("【结社战线】扫荡面板未打开，补点一次后再判")
        if not _click_and_expect(tpl_saodang, tpl_panel, expect_timeout=PANEL_TIMEOUT):
            log("【结社战线】两次点击后扫荡面板仍未打开，视为无剩余次数")
            return False

    click_position(_find(tpl_saodang_max), 1.0)   # 一次选到最大档
    btn_pos = _find(tpl_saodang_btn, SAODANG_BTN_THRESHOLD)
    if btn_pos is None:
        log("【结社战线】扫荡面板内未找到「扫荡」按钮")
    else:
        click_position(btn_pos, 2.0, twice=False)
        if _find(tpl_saodang_done, timeout=15) is not None:
            # 这条日志原先写「剩余扫荡次数已用完」，位置又紧跟在「本场失败」之后，
            # 读起来像「没扫就没了」（2026-11-11 用户据此反馈「报完成了但没扫荡」）。
            # 它其实是扫荡成功、次数清零的结果，明确写成完成态。
            log("【结社战线】扫荡完成，当日剩余次数已清零")
        else:
            log("【结社战线】未看到「扫荡完成」结算，可能扫荡未执行")
        dismiss_popup_away_from()

    _back_to_main()
    return True


def main():
    """执行结社战线每日流程（挑战到失败 + 扫满剩余次数），跑完返回 True。"""
    log("【结社战线】开始执行...")

    if not flow_enter_guild_play(tpl_card, "结社战线"):
        # 2026-11-08 实跑：入口卡片可能因活动排期/版本改版不存在，属「当日无此玩法」，
        # 按跳过处理（返回 True），不让整轮任务因入口缺失而标记失败。
        log("【结社战线】入口卡片不可用，本日跳过")
        flow_return_main()
        return True
    if _find(tpl_title, timeout=SETTLE_DELAY + PANEL_TIMEOUT) is None:
        log("【结社战线】未进入结社战线主界面，本日跳过")
        flow_return_main()
        return True

    wins = _challenge_until_lose()
    swept = _sweep_remaining()
    log(f"【结社战线】结束：挑战胜 {wins} 场，扫荡{'已执行' if swept else '无剩余次数'}")

    check_and_handle_libao()
    flow_return_main()
    return True


if __name__ == "__main__":
    main()
