"""好友奖励流程模块。

从主界面进入 菜单 → 社交 → 一键赠礼，清理结算弹窗后经 flow_return_main 返回主界面。
目的：领取好友赠送的奖励（不含自身资源消耗）。入口 main() 由 GUI「好友奖励」脚本调用。

实测（2026-11-04）：
- 「一键赠礼并收取」点**一次**就把当天可赠可收的全部处理完，按钮随即变灰（notyijianzengli），
  收礼进度 2/10 直接跳到 10/10。
- 顶部「收礼进度」的宝箱在满 10 时**自动入账**（当场弹「获得奖励」，宝箱变打勾态），
  不需要再点一次宝箱——所以本模块不去点它，避免把打勾宝箱当可领。
- 好友面板另两个页签（公会成员 / 家园借用）实测没有任何领取控件，家园借用只是申请列表。
"""

import os
import time

from common import (
    find_center,
    game_client_region,
    get_templates_dir,
    send_coord,
    tap_hud_entry,
    wait_and_click,
)
from flow_enter import flow_return_main

# 模板路径
templates_dir = get_templates_dir()

CLOSE_POPUP = os.path.join(templates_dir, "dianjikongbaichuguanbi.png")
YIJIANZENGLI = os.path.join(templates_dir, "yijianzengli.png")
NOTYIJIANZENGLI = os.path.join(templates_dir, "notyijianzengli.png")

# 好友面板里除「一键赠礼并收取」之外的额外奖励：单独的「领取」按钮、满箱宝箱，
# 以及宝箱点开后弹出的「收获奖励」
LINGQU = os.path.join(templates_dir, "lingqu.png")
BAOXIANG_FULL = os.path.join(templates_dir, "baoxiang_full.png")
SHOUHUOJIANGJI = os.path.join(templates_dir, "shouhuojiangli.png")

# 额外奖励最多扫描多少次：找不到即停，上限只防界面不刷新时死循环
MAX_FRIEND_REWARD_SCANS = 5


# 一键赠礼并收取最多点几次：实测一次就够，留点余量防它分「发送 / 收取」两段
MAX_GIFT_CLICKS = 3

# 进入好友面板的最多尝试次数，以及每轮等待面板按钮出现的时长（秒）
ENTER_ATTEMPTS = 2
PANEL_WAIT = 6.0

# 主界面右下角的好友（兜帽）图标——好友面板的直达入口，实测客户区 (1566,702)。
# 菜单→社交 要连中 caidan、shejiao 两处模板，任一处失效就进不去，这里作兜底。
FRIENDS_HUD_POS = (1566, 702)


def _close_popups(timeout=8.0):
    """循环点击「点击空白处关闭」，直到弹窗消失（连续 2 秒不再出现则停止）。"""
    start = time.time()
    last_seen = time.time()
    while time.time() - start < timeout:
        pos = find_center(CLOSE_POPUP, 0.8)
        if pos:
            print("【好友奖励】检测到弹窗「点击空白处关闭」，点击关闭")
            send_coord(pos[0], pos[1])
            last_seen = time.time()
            time.sleep(1.0)
        else:
            if time.time() - last_seen > 2.0:
                break
            time.sleep(0.5)
    print("【好友奖励】弹窗清理完成")


def _friends_panel_visible():
    """好友面板是否已打开：可赠（绿色按钮）或已赠完（灰色按钮）都算进来了。"""
    return bool(find_center(YIJIANZENGLI, threshold=0.8) or find_center(NOTYIJIANZENGLI, threshold=0.8))


def _wait_friends_panel(timeout=6.0):
    """轮询等待好友面板按钮出现。

    2026-11-10 实机：点「社交」后固定 sleep 2 秒再查一次，面板没渲染完就直接判
    「未检测到一键赠礼」并终止——现场截图还停在家园主界面（点击被激活窗口吞掉）。
    入门这一步必须轮询，不能只看一眼。
    """
    deadline = time.time() + timeout
    while True:
        if _friends_panel_visible():
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.5)


def _open_friends_via_hud(retries=2):
    """兜底入口：点主界面右下角好友图标直达好友面板。

    角落 HUD 图标在窗口未前台时，第一次点击会被系统当成激活点击吞掉（实测单次点击
    完全无反应），所以每轮连点两下，再用按钮是否出现来确认，不靠「点了就当进去了」。
    """
    def click(corner_pos):
        region = game_client_region()
        pos = (region[0] + corner_pos[0], region[1] + corner_pos[1])
        send_coord(pos[0], pos[1])
        time.sleep(0.4)
        send_coord(pos[0], pos[1])
        time.sleep(2.0)

    if not tap_hud_entry(
        FRIENDS_HUD_POS,
        _friends_panel_visible,
        retries=retries,
        click=click,
        log_func=lambda attempt: print(f"【好友奖励】第 {attempt} 次点主界面好友图标后未见好友面板按钮"),
    ):
        return False
    print("【好友奖励】经主界面好友图标进入好友面板")
    return True


def _collect_gifts():
    """反复点「一键赠礼并收取」直到按钮消失，返回点击次数。

    实测点一次当天就全部赠完并收完（按钮随即变灰），但该按钮分「发送 / 收取」两段时
    一次未必点完，所以点到消失为止，并用 MAX_GIFT_CLICKS 兜住异常刷新不了的情况。
    """
    clicks = 0
    while clicks < MAX_GIFT_CLICKS:
        pos = find_center(YIJIANZENGLI, threshold=0.8)
        if not pos:
            break
        print(f"【好友奖励】检测到 yijianzengli，第 {clicks + 1} 次点击一键赠礼并收取")
        send_coord(pos[0], pos[1])
        clicks += 1
        time.sleep(2)
        _close_popups()
    return clicks


def _claim_friend_rewards():
    """好友面板里除「一键赠礼并收取」之外的单点奖励。

    一键赠礼只处理每日赠礼/收礼进度，面板里还可能残留单独的「领取」按钮与满箱宝箱；
    命中就点并清理弹窗，找不到即停。宝箱点开后若弹「收获奖励」再补点一次。
    返回本次领取的奖励项数。
    """
    claimed = 0
    for _ in range(MAX_FRIEND_REWARD_SCANS):
        pos = None
        for template in (LINGQU, BAOXIANG_FULL):
            pos = find_center(template, threshold=0.8)
            if pos:
                break
        if not pos:
            break
        print(f"【好友奖励】检测到好友面板额外奖励，第 {claimed + 1} 次点击")
        send_coord(pos[0], pos[1])
        claimed += 1
        time.sleep(2)
        _close_popups()
        shouhuo = find_center(SHOUHUOJIANGJI, threshold=0.8)
        if shouhuo:
            print("【好友奖励】检测到「收获奖励」，点击并清理弹窗")
            send_coord(shouhuo[0], shouhuo[1])
            time.sleep(1)
            _close_popups()
    print(f"【好友奖励】好友面板额外奖励领取 {claimed} 项")
    return claimed


def _enter_friends_panel():
    """菜单 → 社交 → 校验好友面板；任一级失败退回主界面好友图标直达。

    2026-11-10 实机日志：08:20:55 点菜单、08:20:58 点社交，08:21:00 就报
    「未检测到一键赠礼并终止」，而现场截图仍停在家园主界面——那次点击被激活窗口
    吞掉了。旧实现把 send_coord 当成功，于是整天没送礼也没收礼。改为逐级校验 + 补点。
    """
    caidan_path = os.path.join(templates_dir, "caidan.png")
    if not wait_and_click(caidan_path, "菜单"):
        print("【好友奖励】未找到菜单(caidan)，改用主界面好友图标直达")
        return _open_friends_via_hud()
    print("【好友奖励】已进入菜单，等待 2 秒...")
    time.sleep(2)

    shejiao_path = os.path.join(templates_dir, "shejiao.png")
    for attempt in range(1, ENTER_ATTEMPTS + 1):
        if not wait_and_click(shejiao_path, f"社交({attempt})", timeout=5.0):
            print("【好友奖励】未找到社交(shejiao)，改用主界面好友图标直达")
            return _open_friends_via_hud()
        print(f"【好友奖励】已点击「社交」（第 {attempt} 次），等待好友面板按钮...")
        if _wait_friends_panel(PANEL_WAIT):
            print("【好友奖励】已进入好友面板")
            return True
        print(f"【好友奖励】第 {attempt} 次点「社交」后未出现好友面板按钮，补点")

    print("【好友奖励】菜单→社交 始终没进好友面板，改用主界面好友图标直达")
    return _open_friends_via_hud()


def main():
    print("【好友奖励】开始执行好友奖励任务...")

    if not _enter_friends_panel():
        print("【好友奖励】两条入口都没能进入好友面板，任务终止")
        return False

    # _enter_friends_panel 已确认面板按钮可见，这里直接取坐标即可
    yijianzengli_pos = find_center(YIJIANZENGLI, threshold=0.8)
    notyijianzengli_pos = find_center(NOTYIJIANZENGLI, threshold=0.8)

    gifts_ok = True
    if yijianzengli_pos:
        clicks = _collect_gifts()
        if clicks:
            print(f"【好友奖励】一键赠礼并收取共点击 {clicks} 次，结算弹窗已清理")
        else:
            # 2026-11-10：按钮「首次检查后就不可见」多半是点击被意外弹框吞掉或界面
            # 还没加载完，旧实现直接「视为已处理」→ 奖励没领却报成功。这里复核一次。
            print("【好友奖励】按钮在首次检查后就不可见，复核一次")
            time.sleep(1.5)
            _close_popups()
            clicks = _collect_gifts()
            if clicks:
                print(f"【好友奖励】复核后完成一键赠礼并收取 {clicks} 次点击")
            elif find_center(YIJIANZENGLI, threshold=0.8):
                print("【好友奖励】一键赠礼按钮仍可见却点不掉，任务未完成")
                gifts_ok = False
            else:
                print("【好友奖励】复核确认按钮已消失，视为已处理")
    elif notyijianzengli_pos:
        print("【好友奖励】检测到 notyijianzengli（已赠礼/无需赠礼），跳过赠礼，直接进入退出流程")
    else:
        print("【好友奖励】未检测到 yijianzengli 或 notyijianzengli，任务终止")
        return False

    # 一键赠礼只处理每日赠礼/收礼进度，面板里还可能残留单独的「领取」与满箱宝箱
    _claim_friend_rewards()

    # 退出好友列表
    print("【好友奖励】点击 exitck 退出好友列表")
    exitck_path = os.path.join(templates_dir, "exitck.png")
    if not wait_and_click(exitck_path, "exitck"):
        print("【好友奖励】未找到 exitck（可能已在社交主页），继续执行退出流程")
    time.sleep(2)

    # 退出社交界面
    print("【好友奖励】点击 exit 退出社交界面")
    exit_path = os.path.join(templates_dir, "exit.png")
    if not wait_and_click(exit_path, "exit"):
        print("【好友奖励】未找到 exit（可能已回到主界面），继续执行")
    time.sleep(2)

    # 兜底：清理残留弹窗并回到主界面，避免卡在好友/社交界面
    print("【好友奖励】清理残留弹窗并回到主界面...")
    _close_popups()
    ok = flow_return_main()
    if ok:
        print("【好友奖励】好友奖励任务执行完成！已回到主界面")
    else:
        print("【好友奖励】好友奖励任务执行完成，但未能确认回到主界面，请检查游戏画面")
    if not gifts_ok:
        print("【好友奖励】一键赠礼未确认完成，任务标记失败")
        return False
    return True
