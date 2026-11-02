# D:\workspace\afk-journey-merlin-auto\yuanwangdan.py
"""家园愿望单（Homestead 订单）自动交付流程模块。

流程（在家园主界面执行）：
1. 点击左侧「愿望单」入口(yuanwangdan)进入愿望单界面；
2. 循环「一键选择」(yijianxuanze) → 「交付」(xinyuandanjiaofu) → 关闭「完成愿望单」结算
   (xinyuandanwancheng)，逐单交付，直到资源不足；
3. 资源不足时游戏弹出「当前资源不足，可从以下途径获取」(xinyuandanbuzu)，
   点击首条途径的箭头(tujingjiantou)即自动寻路到对应生产建筑（厨房 / 锻造工坊 / 炼金工坊）；
4. 建筑内把数量档点到「x10」（x1 → x5 → x10，进建筑固定是 x1，故点两下）后点「开始烹饪」
   (kaishipengren)制作 10 份，完成后逐层返回家园、重新进入愿望单继续交付；
5. 交付批数达到上限、制作次数达到上限、连续多轮界面无变化或界面无法识别时结束，并回主界面。

入口 main() 由 GUI「家园愿望单」脚本调用（daily_reset，每天执行一次）。

设计要点：
- 状态判定全部基于模板匹配（项目无 OCR 依赖），判定顺序为 领奖 > 不足弹框 > 已选待交付 >
  待选择 > 结算。前四态都靠「认得出具体控件」的强判据；结算放最后，因为它还依赖
  「有『点击空白处关闭』提示且其余四态都已排除」的兜底分支——结算标题带流光动画，
  实测同一模板连续帧匹配分在 0.82–0.95 抖动，单靠标题会在 0.8 阈值上随机漏判。
  弹窗压住面板时面板按钮只会匹配到 0.43–0.50（实测），不会与结算抢判。
- 「一键选择」只填入需求槽并把按钮变为橙色「交付」，必须再点一次才真正提交——这是本流程
  与「一次点击即完成」的差异点，只点一次会停在已选择状态空转。
- 进度奖励只在「进度可能刚变」时试领（开局 + 每次交付后），不是每轮都试：礼盒常亮但无
  可领档位时，每轮白点一次既拖慢流程、又会把额度提前耗光导致后面真解锁的档位领不到。
- 所有点击坐标均由模板匹配得到（find_center_silent 返回全屏坐标），不用硬编码屏幕坐标：
  结算 / 领奖弹窗直接用「点击空白处关闭」提示定位关闭点，返回箭头用 fanhui 模板定位。
- 数量档位为 x1 → x5 → x10 循环，且进建筑时固定回到 x1，故直接点两下取 x10，不再用
  「最大档」模板反查——反查失败时会继续点，可能从 x10 又循环回 x1，越确认越偏。
- 制作中「开始烹饪」按钮会被替换为进度指示，故以该按钮「消失→重新出现」作为完成信号；
  「消失」这一步是必须的判据，否则点击未生效时会因按钮一直在而被误判成制作完成。
- 模板与偏移量按 1600×900 客户区采集：本任务首批模板曾在 1302×1080 窗口下采集，而游戏 UI
  不随窗口等比缩放，换分辨率后整套模板与像素偏移全部失效（表现为「已点击愿望单入口 →
  未进入愿望单界面」）。改分辨率时这批模板需整体重采。
"""

import time

from common import (
    check_stop,
    click_position,
    find_center_silent,
    get_template_path,
    invalidate_screenshot_cache,
    log,
)
from flow_enter import flow_return_main

# 模板路径
tpl_entry = get_template_path("yuanwangdan.png")            # 家园左侧「愿望单」入口
tpl_one_key = get_template_path("yijianxuanze.png")         # 愿望单「一键选择」
tpl_deliver = get_template_path("xinyuandanjiaofu.png")     # 已选择后的橙色「交付」
tpl_result = get_template_path("xinyuandanwancheng.png")    # 「完成愿望单」结算
tpl_lack = get_template_path("xinyuandanbuzu.png")          # 「当前资源不足」弹框标题
tpl_path_arrow = get_template_path("tujingjiantou.png")     # 途径条目右侧箭头
tpl_cook = get_template_path("kaishipengren.png")           # 建筑内「开始烹饪」
tpl_back = get_template_path("fanhui.png")                  # 建筑内左下角返回箭头
tpl_label = get_template_path("xinyuandanbiaoti.png")       # 左上角「愿望单」标题标签（定位礼盒点击点）
tpl_claim = get_template_path("huodejiangli.png")           # 领奖弹窗「获得奖励」标题
tpl_close_popup = get_template_path("dianjikongbaichuguanbi.png")

MATCH_THRESHOLD = 0.8
GIFT_CLICK_OFFSET = (120, 40)  # 礼盒可领取时的点击点，相对「愿望单」标题中心（1600×900 实测有效点 2629,135 - 标题中心 2509,95）
MAX_ORDERS = 20           # 单次任务最多交付订单数，防止无限刷单
MAX_CRAFTS = 5            # 单次任务最多制作次数，防止资源误消耗失控
MAX_CLAIMS = 10           # 单次任务最多成功领奖次数（愿望单奖励档位逐级提升）
MAX_IDLE_ROUNDS = 8       # 同一状态连续无变化的最大轮数，超限即判定卡死
SETTLE_DELAY = 2.0        # 界面切换后的稳定等待
DELIVER_DELAY = 3.0       # 交付后等待结算动画
CRAFT_ENTRY_TIMEOUT = 40  # 自动寻路到建筑并打开制作界面的等待上限
CRAFT_START_TIMEOUT = 10  # 点「开始烹饪」后等待按钮消失（确认这批真的开始）的上限
CRAFT_DONE_TIMEOUT = 180  # 一次批量制作的完成等待上限（实测 x10 一批可超过 90 秒）
QTY_CLICK_TIMES = 2       # 数量档 x1 → x5 → x10 循环，进建筑固定是 x1，故点两下即 x10
QTY_BUTTON_OFFSET = (110, -10)   # 数量按钮相对「开始烹饪」中心的偏移（1600×900 实测：烹饪 2896,859 / 数量 3006,849）

# 界面状态
STATE_CLAIM = "claim"        # 领奖弹窗「获得奖励」
STATE_RESULT = "result"      # 完成结算
STATE_LACK = "lack"          # 资源不足弹框
STATE_DELIVER = "deliver"    # 已填入需求，等待交付
STATE_ONE_KEY = "one_key"    # 待一键选择


def _find(template_path, timeout=0, threshold=MATCH_THRESHOLD):
    return find_center_silent(template_path, threshold, timeout=timeout)


def _click(pos, wait=SETTLE_DELAY):
    """点击并等待界面响应；连点两次的补偿见 common.click_position。

    仅用于幂等操作（按钮 / 弹窗空白 / 礼盒）；跳转类按钮（如愿望单入口）请用 _click_once。
    """
    return click_position(pos, wait, twice=True)


def _click_once(pos, wait=SETTLE_DELAY):
    """单次点击并等待界面响应；跳转类按钮专用，避免连点触发"进入后又退出"。"""
    return click_position(pos, wait, twice=False)


def _wait_gone(template_path, timeout):
    """在 timeout 秒内等待模板从画面上消失；消失返回 True，超时仍在返回 False。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        check_stop()
        if _find(template_path) is None:
            return True
        time.sleep(0.5)
    return _find(template_path) is None


def _close_by_blank_hint():
    """用「点击空白处关闭」提示本身定位并关闭结算 / 领奖弹窗。

    早先按「弹窗标题 + 固定偏移」推算关闭点，但结算标题带流光动画（实测匹配分在 0.82–0.95
    抖动）、偏移量又随窗口分辨率变化；改点提示文字更稳。该提示在屏幕底部居中，而愿望单面板的
    主按钮（一键选择 / 交付）在其上方 60 余像素，不会像结社战线「扫荡」那样与热区重合，
    所以这里可以直接点提示中心。
    """
    return _click(_find(tpl_close_popup), SETTLE_DELAY)


def _panel_state():
    """判定愿望单界面当前状态，返回 (状态, 锚点坐标)；无法识别返回 (None, None)。

    判定顺序：领奖 > 不足弹框 > 交付 > 一键选择 > 结算。前四者都是「认得出具体控件」的
    强判据；结算放最后，因为它除了标题还靠「点击空白处关闭」提示兜底——结算标题带流光
    动画，实测同一模板连续帧匹配分在 0.82–0.95 抖动，单靠标题会在 0.8 阈值上随机漏判。
    弹窗盖住面板时面板按钮会被压暗到 0.43–0.50（实测），不会与结算抢判。
    """
    pos = _find(tpl_claim)
    if pos is not None:
        return STATE_CLAIM, pos
    pos = _find(tpl_lack)
    if pos is not None:
        return STATE_LACK, pos
    pos = _find(tpl_deliver)
    if pos is not None:
        return STATE_DELIVER, pos
    pos = _find(tpl_one_key)
    if pos is not None:
        return STATE_ONE_KEY, pos
    if _find(tpl_result) is not None or _find(tpl_close_popup) is not None:
        # 结算 / 领奖之外的弹窗都会留下「点击空白处关闭」提示；上面几态都已排除，
        # 剩下的带提示弹窗按结算处理（关闭后重新判定），锚点无意义故返回 None
        return STATE_RESULT, None
    return None, None


def _claim_reward(label_pos):
    """尝试点礼盒领取心愿单进度奖励：点礼盒 → 关闭「获得奖励」弹窗，返回是否实际领取。

    礼盒图标在不同档位下外观不同（第一档金色心形、第二档青色宝石），模板匹配无法跨档位；
    改为用固定的「愿望单」标题标签做锚点、按偏移点击其右侧礼盒区域（实测有效点）。
    已领取状态下点击无副作用（无弹窗），故可以每轮安全尝试，以弹出「获得奖励」为准。
    """
    gift_pos = (label_pos[0] + GIFT_CLICK_OFFSET[0], label_pos[1] + GIFT_CLICK_OFFSET[1])
    _click(gift_pos, 1.5)
    claim_pos = _find(tpl_claim, timeout=1.5)
    if claim_pos is None:
        return False
    log("【家园愿望单】愿望单进度奖励已领取")
    _close_by_blank_hint()
    return True


def _ensure_panel():
    """确保处于愿望单界面：已在则直接返回，否则点击家园左侧入口进入。

    上次运行中断可能停在「完成愿望单」结算界面，此时先关闭结算再判定，
    避免把结算界面误判成「不在愿望单界面」而重新点入口。
    """
    if _find(tpl_result) is not None or _find(tpl_close_popup) is not None:
        _close_by_blank_hint()

    if _find(tpl_one_key) or _find(tpl_deliver):
        log("【家园愿望单】已在愿望单界面")
        return True

    entry_pos = None
    deadline = time.time() + 15
    while time.time() < deadline:
        entry_pos = _find(tpl_entry)
        if entry_pos is not None:
            break
        time.sleep(0.5)
    if entry_pos is None:
        log("【家园愿望单】未找到愿望单入口，任务终止")
        return False
    _click_once(entry_pos, SETTLE_DELAY)
    log("【家园愿望单】已点击愿望单入口")
    # 首次点击可能被系统吞掉（窗口未激活），重试一次；不连点两次：入口是跳转类按钮，
    # 连点会"进入愿望单后再退出"。
    if _find(tpl_one_key, timeout=5) is None and _find(tpl_deliver, timeout=2) is None:
        _click_once(entry_pos, SETTLE_DELAY)
    if _find(tpl_one_key, timeout=10) or _find(tpl_deliver, timeout=3):
        return True
    log("【家园愿望单】未进入愿望单界面，任务终止")
    return False


def _back_to_homestead():
    """从生产建筑逐层返回家园主界面（愿望单入口重新可见）。

    生产界面分两层：产品制作界面 → 产品选择列表 → 家园，故最多连点 3 次返回箭头。
    """
    for _ in range(3):
        if _find(tpl_entry):
            return True
        back_pos = _find(tpl_back)
        if back_pos is None:
            break
        _click(back_pos, SETTLE_DELAY)
    if _find(tpl_entry, timeout=5):
        return True
    log("【家园愿望单】返回家园失败，尝试兜底回主界面")
    flow_return_main()
    return _find(tpl_entry, timeout=5) is not None


def _craft_from_lack():
    """资源不足弹框 → 自动寻路 → 批量制作 10 份 → 返回并重进愿望单。

    返回 True 表示制作与返回流程已走完（库存是否补足由主循环重新判定）。
    """
    arrow_pos = _find(tpl_path_arrow)
    if arrow_pos is None:
        log("【家园愿望单】未找到「制作获取」途径入口，无法自动制作")
        return False
    log("【家园愿望单】资源不足，点击途径入口自动寻路至生产建筑")
    _click(arrow_pos, 1.0)

    cook_pos = _find(tpl_cook, timeout=CRAFT_ENTRY_TIMEOUT)
    if cook_pos is None:
        log("【家园愿望单】未进入生产界面（可能被弹窗遮挡或寻路中断）")
        return False
    log("【家园愿望单】已进入生产界面，切换批量档位")

    qty_pos = (cook_pos[0] + QTY_BUTTON_OFFSET[0], cook_pos[1] + QTY_BUTTON_OFFSET[1])
    # 数量档是 x1 → x5 → x10 循环，且进建筑时固定回到 x1，所以「点满两下」就确定是 x10。
    # 原先靠 zhizuox10 模板确认档位，但该模板只匹配得到 x1 之外的外观时会反复重点，
    # 反而可能从 x10 再循环回 x1；改成固定次数、不依赖档位识别。
    for _ in range(QTY_CLICK_TIMES):
        click_position(qty_pos, 1.0)
        invalidate_screenshot_cache()

    log("【家园愿望单】开始批量制作")
    _click(cook_pos, 1.0)
    # 制作中「开始烹饪」会被进度指示替换。必须先确认它真的「消失」了——那才说明这批已开始；
    # 少了这一步，点击没生效时会因为按钮一直在而被下面的「重新出现」立刻判成制作完成，白跑一轮。
    if not _wait_gone(tpl_cook, CRAFT_START_TIMEOUT):
        log("【家园愿望单】点「开始烹饪」后按钮未消失，制作未开始，停止制作流程")
        return False
    if _find(tpl_cook, timeout=CRAFT_DONE_TIMEOUT) is None:
        log("【家园愿望单】制作完成等待超时，停止制作流程")
        return False
    log("【家园愿望单】批量制作完成")

    if not _back_to_homestead():
        log("【家园愿望单】未能回到家园，停止制作流程")
        return False
    return _ensure_panel()


def main():
    """执行家园愿望单自动交付（含缺口自动制作），至少交付一单返回 True。"""
    log("【家园愿望单】开始执行...")

    if not _ensure_panel():
        flow_return_main()
        return False

    delivered = 0
    crafts = 0
    claims = 0
    claim_due = True          # 进度只在交付后才会涨，故只在开局与每次交付后试领一次
    idle_rounds = 0
    last_state = None

    while delivered < MAX_ORDERS:
        check_stop()

        # 试领进度奖励：点礼盒，弹出「获得奖励」才算领取（已领取状态下点击无副作用）。
        # 只在「进度可能刚变」时试，而不是每轮都试——礼盒常亮但无可领档位时，每轮白点一次
        # 既拖慢流程，也会把按「尝试次数」计的额度提前耗光，导致后面真解锁的档位领不到。
        if claim_due and claims < MAX_CLAIMS:
            claim_due = False
            label_pos = _find(tpl_label)
            if label_pos is not None and _claim_reward(label_pos):
                claims += 1
                idle_rounds = 0
                last_state = None
                continue

        state, anchor = _panel_state()

        if state == last_state:
            idle_rounds += 1
            if idle_rounds >= MAX_IDLE_ROUNDS:
                log(f"【家园愿望单】界面连续 {MAX_IDLE_ROUNDS} 轮无变化（{state}），判定卡死并结束")
                break
        else:
            idle_rounds = 0
            last_state = state

        if state == STATE_CLAIM:
            _close_by_blank_hint()
            continue

        if state == STATE_RESULT:
            # 结算界面：点空白处关闭，回到愿望单或下一个订单
            _close_by_blank_hint()
            continue

        if state == STATE_ONE_KEY:
            # 必须用单击：缺料时点「一键选择」会弹出「当前资源不足」弹框，而 _click 的
            # 连点补偿第二下正好落在该弹框上把它关掉，于是状态机永远只看到 one_key，
            # 既进不了补货分支也判不出「这单做不了」，最后白耗 8 轮空转退出（实测踩过）。
            # 单击后重新判定状态：出现「交付」= 填入成功；出现「不足弹框」= 走补货；
            # 仍是 one_key 则说明首次点击被窗口激活吞掉，重试。
            for _ in range(3):
                _click_once(anchor, SETTLE_DELAY)
                next_state, next_anchor = _panel_state()
                if next_state == STATE_ONE_KEY:
                    anchor = next_anchor or anchor
                    continue
                break
            continue

        if state == STATE_DELIVER:
            _click(anchor, DELIVER_DELAY)
            delivered += 1
            claim_due = True   # 交付会让进度条前进，可能点亮下一档礼盒
            log(f"【家园愿望单】第 {delivered} 单已交付")
            continue

        if state == STATE_LACK:
            if crafts >= MAX_CRAFTS:
                log(f"【家园愿望单】已达单次制作上限 {MAX_CRAFTS} 次，本次停止补货")
                break
            crafts += 1
            log(f"【家园愿望单】库存不足，开始第 {crafts} 次自动制作")
            if not _craft_from_lack():
                break
            idle_rounds = 0
            last_state = None
            continue

        # 既非结算/不足，也无可操作按钮：可能是界面动画、加载中，或游戏窗口被其它窗口遮挡
        # （带「点击空白处关闭」提示的弹窗已在 _panel_state 里归入 STATE_RESULT，不会走到这里）
        if idle_rounds < MAX_IDLE_ROUNDS:
            # 游戏窗口被切走时会短暂取不到画面，等待后再试；连续多轮仍无画面才放弃
            log("【家园愿望单】暂未识别到界面，等待重试")
            time.sleep(1.0)
            continue
        log("【家园愿望单】未能识别当前界面，结束本次任务")
        break

    log(f"【家园愿望单】结束：本次交付 {delivered} 单，自动制作 {crafts} 次，领取奖励 {claims} 次")

    # 最后一单交付后循环条件即失效，此时结算界面仍然覆盖在愿望单上，需单独关闭，
    # 否则后续任务的「回主界面」流程会被结算界面挡住（退出模板均不匹配该界面）。
    for _ in range(3):
        if _find(tpl_result) is None and _find(tpl_close_popup) is None:
            break
        _close_by_blank_hint()

    # 收尾：家园视图下「玩法目录」(wanfamulu) 匹配度不足 0.5，调用 recover 会空转十余秒，
    # 故仅当已离开家园时才执行兜底回主界面；该任务在 GUI 中固定排在执行顺序末尾。
    if _find(tpl_entry) is None:
        flow_return_main()
    return delivered > 0


if __name__ == "__main__":
    main()
