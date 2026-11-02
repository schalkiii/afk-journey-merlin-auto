# D:\workspace\afk-journey-merlin-auto\lieshouxunshang.py
"""狩猎悬赏每日流程：用掉自己的「搜寻精怪」次数，再用「加入」参加队友的悬赏。

流程（自主界面起）：
1. flow_enter_guild_play 点「狩猎悬赏」卡片——该卡片只做一件事：把角色传送进公会大厅；
2. 大厅里再点「狩猎悬赏」招牌才进悬赏面板（招牌是 2D 贴字，传送后镜头未停稳时会漂移，
   故先轮询等它出现，点一次没进面板就重找再点一次）；
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

入口 main() 由 GUI「狩猎悬赏」脚本调用（daily_reset，每天执行一次）。
"""

import time

from common import (
    check_stop,
    click_position,
    dismiss_popup_away_from,
    find_center_silent,
    get_template_path,
    log,
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
    """点卡片传送进公会大厅 → 点大厅招牌 → 进入悬赏面板，成功返回 True。"""
    if not flow_enter_guild_play(tpl_card, "狩猎悬赏"):
        return False

    for _ in range(2):
        check_stop()
        hall_pos = find_center_silent(tpl_hall, MATCH_THRESHOLD, timeout=HALL_TIMEOUT)
        if hall_pos is None:
            log("【狩猎悬赏】公会大厅内未找到狩猎悬赏招牌")
            return False
        click_position(hall_pos, SETTLE_DELAY, twice=False)
        if _find(tpl_title, timeout=PANEL_TIMEOUT) is not None:
            return True
    log("【狩猎悬赏】点招牌后未进入悬赏面板")
    return False


def _close_settlements():
    """关掉抽取结算弹窗（可能连弹两层），直到面板标题重新可见。"""
    for _ in range(MAX_POPUP_CLOSES):
        check_stop()
        if _find(tpl_title) is not None:
            return True
        if not dismiss_popup_away_from():
            time.sleep(1.0)
    return _find(tpl_title) is not None


def _use_own_searches():
    """抽光自己的「搜寻精怪」次数，返回抽取次数。"""
    searched = 0
    while searched < MAX_SEARCHES:
        check_stop()
        search_pos = _find(tpl_search)
        if search_pos is None:
            break   # 按钮变灰：自己的次数已用尽
        click_position(search_pos, SETTLE_DELAY, twice=False)
        searched += 1
        log(f"【狩猎悬赏】第 {searched} 次搜寻精怪完成")
        if not _close_settlements():
            log("【狩猎悬赏】结算弹窗未能关闭，停止搜寻")
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
    while joined < MAX_JOINS:
        check_stop()
        join_pos = find_center_silent(tpl_join, JOIN_THRESHOLD, region=region)
        if join_pos is None:
            break
        click_position(join_pos, SETTLE_DELAY)
        joined += 1
        log(f"【狩猎悬赏】已参加第 {joined} 个队友悬赏")
    return joined


def main():
    """执行狩猎悬赏每日流程（自己的搜寻次数 + 参加队友悬赏），跑完返回 True。"""
    log("【狩猎悬赏】开始执行...")

    if not _enter_panel():
        check_and_handle_libao()
        flow_return_main()
        return False

    searched = _use_own_searches()
    joined = _join_others()
    log(f"【狩猎悬赏】结束：自己搜寻 {searched} 次，参加队友 {joined} 次")

    for _ in range(3):
        if _find(tpl_back) is None:
            break
        click_position(_find(tpl_back), SETTLE_DELAY)

    check_and_handle_libao()
    flow_return_main()
    return True


if __name__ == "__main__":
    main()
