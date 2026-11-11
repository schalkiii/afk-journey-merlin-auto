# D:\workspace\afk-journey-merlin-auto\flow_gonghui.py
"""公会玩法入口共用流程：主界面 → 玩法目录 → 「公会玩法」页签 → 指定玩法卡片。

结社战线与狩猎悬赏两个公会日常都从这条路径进入，抽成一处以免两份实现分叉。

设计要点：
- 「公会玩法」页签有已激活 / 未激活两种外观（文字配色与底纹不同），单一模板会互相误命中：
  未激活页签的模板在已激活界面上最高只能匹配到左侧「常规玩法」页签（实测 0.85），
  反之亦然。故两种外观各存一份模板（gonghuiwanfa / gonghuiwanfaactive），并用 0.95 的
  高阈值把两者分开——先判「已激活」（说明已在公会玩法页，无需再点），再点「未激活」。
- 卡片本身是跳转类按钮，用单击（twice=False）：连点会「进入后又退出」。是否真的进入
  由各调用方按自己的落地界面判定（本函数只负责点下去）。

入口 flow_enter_guild_play() 由 jieshezhanxian / lieshouxunshang 调用。
"""

import time

from common import (
    check_stop,
    click_position,
    find_center_silent,
    get_template_path,
    log,
    open_wanfamulu,
    scroll_in_client_region,
)

tpl_catalog_title = get_template_path("wanfamulubiaoti.png")   # 玩法目录面板标题（判断是否已离开目录）
tpl_tab = get_template_path("gonghuiwanfa.png")                # 「公会玩法」页签（未激活）
tpl_tab_active = get_template_path("gonghuiwanfaactive.png")   # 「公会玩法」页签（已激活）

TAB_THRESHOLD = 0.95   # 低于该值会误命中相邻页签，见模块文档
SETTLE_DELAY = 2.0     # 界面切换后的稳定等待


def flow_enter_guild_play(card_template, card_name):
    """从主界面进入公会玩法页并点击目标玩法卡片；点击完成返回 True（落地由调用方校验）。

    卡片查找失败且当前已不在玩法目录时（2026-11-08 实跑：一次误点就把目录关掉、
    界面回到家园），重新进入目录再试一轮，避免单次误点就直接失败。
    """
    for round_no in (1, 2):
        if not open_wanfamulu(threshold=0.7, timeout=8):
            log(f"【公会玩法】未找到玩法目录入口，无法进入{card_name}")
            return False
        time.sleep(SETTLE_DELAY)

        if find_center_silent(tpl_tab_active, TAB_THRESHOLD) is None:
            check_stop()
            tab_pos = find_center_silent(tpl_tab, TAB_THRESHOLD, timeout=5)
            if tab_pos is None:
                log(f"【公会玩法】未找到「公会玩法」页签，无法进入{card_name}")
                return False
            click_position(tab_pos, SETTLE_DELAY)

        check_stop()
        card_pos = find_center_silent(card_template, 0.8, timeout=8)
        if card_pos is None:
            # 逐次下滑、每次检查：一次滚两下会过头（2026-11-10 爬塔实机踩过）
            for scroll_try in range(1, 3):
                log(f"【公会玩法】首屏未找到{card_name}卡片，第 {scroll_try} 次滚动列表再找")
                scroll_in_client_region("down", times=1)
                card_pos = find_center_silent(card_template, 0.8, timeout=3)
                if card_pos is not None:
                    break
        if card_pos is None:
            log(f"【公会玩法】未找到{card_name}入口卡片（第 {round_no} 轮）")
            if round_no == 1 and find_center_silent(tpl_catalog_title, 0.8) is None:
                log("【公会玩法】已不在玩法目录，重开目录再试一轮")
                continue
            return False

        for click_attempt in range(1, 3):
            click_position(card_pos, SETTLE_DELAY, twice=False)
            # 卡片点击可能被窗口激活吞掉（目录仍在原样）：确认已离开目录再交给调用方校验落地。
            if find_center_silent(tpl_catalog_title, 0.8, timeout=0) is None:
                return True
            log(f"【公会玩法】点击{card_name}后目录仍在（第 {click_attempt} 次被吞），补点一次")
        log(f"【公会玩法】多次点击{card_name}后仍停在玩法目录")
        return False
    return False
