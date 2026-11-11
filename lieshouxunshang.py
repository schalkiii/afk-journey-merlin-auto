# D:\workspace\afk-journey-merlin-auto\lieshouxunshang.py
"""狩猎悬赏每日流程：用掉自己的「搜寻精怪」次数，再用「加入」参加队友的悬赏。

流程（自主界面起）：
1. flow_enter_guild_play 点「狩猎悬赏」卡片：新版入口直接打开悬赏面板；旧入口会先
   传送进公会大厅，需再点大厅里的「狩猎悬赏」招牌进入面板——两种落地都兼容；
2. 进面板时可能先弹「狩猎成功」结算/「获得奖励」：在「点击空白处关闭」提示中心连点
   （第一次领奖、第二次关闭），回到可交互的悬赏面板；
3. 悬赏面板：循环点「搜寻精怪」直到按钮变灰（自己次数用尽），每次抽完关掉「发现悬赏目标」结算；
4. 循环在卡片网格里找「加入」按钮并点击，直到找不到（参加次数用尽或已无可参加的悬赏）；
5. 退出到主界面。

设计要点：
- 悬赏奖励是自动结算的：「我的记录」里的奖励图标只读（实测点击无响应），故本流程不做领奖步骤。
- 「发现悬赏目标」结算的「点击空白处关闭」热区（屏幕底部居中）正好压在「搜寻精怪」按钮上
  （y 仅差 2 像素），在热区中心关闭会立刻再抽一次；故统一用 common.dismiss_popup_away_from
  点热区左上方的空白处。
- 「搜寻精怪」按钮在次数耗尽时变灰底深字，与绿底白字的外观差异极大（实测灰态最高只匹配到
  0.53），因此「按钮还能匹配到」本身就是「还有次数」的判据，不需要读数字。
- 「加入」按钮上的数字是自己剩余参加次数（加入3/3 → 加入2/3），会随每次点击变化，
  故模板只裁「加入」两个字；又因该模板很小（48×26），限定在卡片网格区域内匹配，
  区域由面板标题中心推算，不写死屏幕坐标。
- 面板标题在结算弹窗打开时会被压暗到 0.35（匹配不到），故推算网格区域前必须先确认无弹窗。

入口 main() 由 GUI「狩猎悬赏」脚本调用（每天一次，是否执行由用户在列表勾选）。
"""

import time

from common import (
    check_stop,
    click_position,
    dismiss_popup_away_from,
    find_center_silent,
    get_template_path,
    log,
    scroll_in_client_region,
)
from flow_enter import flow_return_main
from flow_gonghui import flow_enter_guild_play
from jiance import check_and_handle_libao

# 模板路径
tpl_card = get_template_path("lieshouxunshang.png")            # 公会玩法页的入口卡片
tpl_hall = get_template_path("lieshouxunshangdating.png")      # 公会大厅内的「狩猎悬赏」招牌
tpl_title = get_template_path("lieshouxunshangbiaoti.png")     # 悬赏面板标题
tpl_search = get_template_path("lieshoujingguai.png")          # 「搜寻精怪」（绿底=还有次数）
tpl_join = get_template_path("lieshoujiaru.png")               # 卡片上的「加入」（不含次数数字）
tpl_back = get_template_path("exit.png")                       # 返回箭头（通用模板）

MATCH_THRESHOLD = 0.8
JOIN_THRESHOLD = 0.85   # 「加入」模板只裁两个字，阈值取高一点防误命中
SETTLE_DELAY = 2.0
HALL_TIMEOUT = 20       # 传送进公会大厅后等镜头停稳、招牌出现的上限
PANEL_TIMEOUT = 12      # 点招牌后进悬赏面板的加载等待上限
MAX_SEARCHES = 15       # 悬赏令持有上限（实测每日恢复 1 点、上限 15），防呆
MAX_JOINS = 3           # 每日可参加队友悬赏的次数（实测 3）
MAX_POPUP_CLOSES = 4    # 一次抽取后可能连弹两层结算
GRID_REGION = (-260, 63, 520, 540)   # 卡片网格相对面板标题中心的 (dx, dy, w, h)


def _find(template, threshold=MATCH_THRESHOLD, timeout=0):
    return find_center_silent(template, threshold, timeout=timeout)


def _enter_panel():
    """点卡片进入悬赏面板，成功返回 True。

    2026-11-06 实测有两种落地：新版入口点卡片后直接进面板（公会大厅的狩猎悬赏招牌
    不再出现），旧路径才是先传送到大厅再点招牌。只等招牌会白等 20 秒后误报「公会
    大厅内未找到狩猎悬赏招牌」，故两种都接受。
    """
    if not flow_enter_guild_play(tpl_card, "狩猎悬赏"):
        return False

    # 先给面板标题 3 秒：直接落地的入口在这一步就能确认，不用白等招牌。
    if _find(tpl_title, timeout=3.0) is not None:
        _close_settlements()
        return _wait_panel_ready()

    for _ in range(2):
        check_stop()
        hall_pos = find_center_silent(tpl_hall, MATCH_THRESHOLD, timeout=HALL_TIMEOUT)
        if hall_pos is None:
            break
        click_position(hall_pos, SETTLE_DELAY, twice=False)
        if _find(tpl_title, timeout=PANEL_TIMEOUT) is not None:
            _close_settlements()
            return _wait_panel_ready()
    log("【狩猎悬赏】公会大厅内未找到狩猎悬赏招牌")
    return False


def _wait_panel_ready():
    """面板标题已出现后，等内容按钮就绪，避免后面 timeout=0 的检测在加载中直接判空。"""
    deadline = time.time() + 6.0
    while time.time() < deadline:
        if _find(tpl_search) is not None or _find(tpl_join, JOIN_THRESHOLD) is not None:
            return True
        time.sleep(0.5)
    log("【狩猎悬赏】面板内容加载较慢，按已进入处理")
    return True


def _close_settlements():
    """关掉结算弹窗（可能连弹两层），直到「点击空白处关闭」提示消失且面板标题可见。

    提示中心与「搜寻精怪」按钮热区只差 2 像素，直接点中心可能多抽一次，故优先点提示
    左上方的空白。但入口的「狩猎成功」结算与「获得奖励」弹窗点空白无效——必须在提示
    中心连点：第一次领奖（弹出获得奖励）、第二次关闭（2026-11-06 实机确认）。
    """
    tpl_hint = get_template_path("dianjikongbaichuguanbi.png")
    hint_center_tried = False
    for _ in range(MAX_POPUP_CLOSES):
        check_stop()
        if _find(tpl_hint) is None and _find(tpl_title) is not None:
            return True
        if not hint_center_tried and dismiss_popup_away_from():
            time.sleep(0.8)
            if _find(tpl_hint) is None:
                return _find(tpl_title) is not None
            hint_center_tried = True
            continue
        hint_pos = _find(tpl_hint)
        if hint_pos is None:
            time.sleep(0.5)
            continue
        click_position(hint_pos, SETTLE_DELAY, twice=False)
        time.sleep(0.8)
    return _find(tpl_hint) is None


_incomplete = {"flag": False, "active": False}


def _dismiss_blocking_popup():
    """清掉意外弹框（「已达成玩家」/「获得奖励」之类），避免它吞掉下一次点击。

    仅在 main() 启动的完整流程里启用（_incomplete["active"]）：单元测试直接调
    _use_own_searches / _join_others 时不触发，避免额外截图与点击桩。
    """
    if not _incomplete["active"]:
        return
    hint = get_template_path("dianjikongbaichuguanbi.png")
    if _find(hint) is None:
        return
    for _ in range(2):
        check_stop()
        dismiss_popup_away_from()
        time.sleep(0.5)
        if _find(hint) is None:
            return
    log("【狩猎悬赏】遮挡弹框清不掉，继续尝试（由面板标题判据兜底）")


def _panel_still_here():
    """本次点击是否真的作用到了悬赏面板上。

    判据是「动作有反馈」，不是「标题还在」：
    - 标题仍可见：点完没弹窗（例如点了没反应的灰按钮），面板还在；
    - 出现「点击空白处关闭」：抽到悬赏/加入成功都会立刻弹结算，弹窗会把面板标题压暗到
      约 0.35（模板匹配不到）。2026-11-11 实机：第一次「搜寻精怪」其实成功了，却因为
      标题被压暗判成「点击被吞」，随后对着旧坐标补点、把面板点没了，整条任务误报未完成。

    只有两者都不成立（既没标题、也没结算弹窗）才是真的被吞掉/离开了面板。
    """
    if not _incomplete["active"]:
        return True
    if _find(tpl_title, timeout=1.5) is not None:
        return True
    return _find(get_template_path("dianjikongbaichuguanbi.png"), timeout=1.0) is not None


def _use_own_searches():
    """抽光自己的「搜寻精怪」次数，返回抽取次数。"""
    searched = 0
    while searched < MAX_SEARCHES:
        check_stop()
        _dismiss_blocking_popup()
        # 首次进入面板时按钮可能还在渲染；给 2 秒轮询，按钮确实变灰才判定次数用尽
        search_pos = _find(tpl_search, timeout=2)
        if search_pos is None:
            break   # 按钮变灰：自己的次数已用尽
        click_position(search_pos, SETTLE_DELAY, twice=False)
        if not _panel_still_here():
            log("【狩猎悬赏】搜寻后面板标题消失，疑似弹框遮挡，清弹框后补点")
            dismiss_popup_away_from()
            click_position(search_pos, SETTLE_DELAY, twice=False)
            if not _panel_still_here():
                log("【狩猎悬赏】补点后仍未恢复面板，判定本次搜寻未生效")
                _incomplete["flag"] = True
                break
        searched += 1
        log(f"【狩猎悬赏】第 {searched} 次搜寻精怪完成")
        if not _close_settlements():
            log("【狩猎悬赏】结算弹窗未能关闭，停止搜寻")
            _incomplete["flag"] = True
            break
    return searched


def _join_others():
    """参加队友悬赏：反复点卡片上的「加入」，直到没有可参加的或达到每日上限。

    加入成功后列表会重排，同一位置可能换成另一张仍可加入的卡片，故不能用「原位置是否还
    匹配得到」判断本次点击是否生效（实测会把真实成功误判成被吞掉，导致少计一次）；
    直接按点击计数，由 MAX_JOINS 上限与「找不到按钮」两个条件收敛。
    """
    title_pos = _find(tpl_title)
    if title_pos is None:
        log("【狩猎悬赏】不在悬赏面板内，跳过参加队友悬赏")
        return 0

    region = (title_pos[0] + GRID_REGION[0], title_pos[1] + GRID_REGION[1],
              GRID_REGION[2], GRID_REGION[3])
    joined = 0
    scroll_rounds = 0
    while joined < MAX_JOINS:
        check_stop()
        _dismiss_blocking_popup()
        # 加入后列表会重排，下一张卡片的按钮可能稍后才出现；给 2 秒轮询避免少计
        join_pos = find_center_silent(tpl_join, JOIN_THRESHOLD, region=region, timeout=2.0)
        if join_pos is not None:
            click_position(join_pos, SETTLE_DELAY)
            if not _panel_still_here():
                log("【狩猎悬赏】加入后面板标题消失，疑似弹框遮挡，清弹框后补点")
                dismiss_popup_away_from()
                click_position(join_pos, SETTLE_DELAY)
                if not _panel_still_here():
                    log("【狩猎悬赏】补点后仍未恢复面板，判定本次加入未生效")
                    _incomplete["flag"] = True
                    break
            joined += 1
            log(f"【狩猎悬赏】已参加第 {joined} 个队友悬赏")
            continue
        # 没找到「加入」：可能有卡片折叠在列表下方（2026-11-08 用户反馈），
        # 先把悬赏卡片网格滚到底再找；滚到底仍没有才认为无可参加。
        if scroll_rounds < 2:
            log("未找到「加入」按钮，下滑悬赏列表到底后再找")
            scroll_in_client_region("down", times=2, region=region)
            scroll_rounds += 1
            continue
        break
    return joined


def main():
    """执行狩猎悬赏每日流程（自己的搜寻次数 + 参加队友悬赏）。

    2026-11-10 起：有动作被意外弹框遮挡且未能恢复时返回 False，不再无条件报成功。
    """
    log("【狩猎悬赏】开始执行...")
    _incomplete["flag"] = False
    _incomplete["active"] = True

    if not _enter_panel():
        # 2026-11-08 实跑：卡片/招牌可能因活动排期或镜头未到位找不到，属「当日无此玩法」，
        # 按跳过处理（返回 True），不让整轮任务因入口缺失而标记失败。
        log("【狩猎悬赏】入口不可用（卡片或招牌缺失），本日跳过")
        check_and_handle_libao()
        flow_return_main()
        _incomplete["active"] = False
        return True

    searched = _use_own_searches()
    joined = _join_others()
    log(f"【狩猎悬赏】结束：自己搜寻 {searched} 次，参加队友 {joined} 次")

    for _ in range(3):
        if _find(tpl_back) is None:
            break
        click_position(_find(tpl_back), SETTLE_DELAY)

    check_and_handle_libao()
    flow_return_main()
    _incomplete["active"] = False
    if _incomplete["flag"]:
        log("【狩猎悬赏】存在被弹框遮挡且未恢复的动作，本次标记未完成")
        return False
    return True


if __name__ == "__main__":
    main()
