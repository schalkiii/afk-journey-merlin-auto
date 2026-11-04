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

# 一键赠礼并收取最多点几次：实测一次就够，留点余量防它分「发送 / 收取」两段
MAX_GIFT_CLICKS = 3

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


def main():
    print("【好友奖励】开始执行好友奖励任务...")

    # 识别并点击菜单
    caidan_path = os.path.join(templates_dir, "caidan.png")
    if not wait_and_click(caidan_path, "菜单"):
        print("【好友奖励】未找到菜单(caidan)，改用主界面好友图标直达")
        if not _open_friends_via_hud():
            print("【好友奖励】两条入口都没能进入好友面板，任务终止")
            return False
    else:
        print("【好友奖励】已进入菜单，等待 2 秒...")
        time.sleep(2)

        # 识别并点击社交
        shejiao_path = os.path.join(templates_dir, "shejiao.png")
        if not wait_and_click(shejiao_path, "社交"):
            print("【好友奖励】未找到社交(shejiao)，改用主界面好友图标直达")
            if not _open_friends_via_hud():
                print("【好友奖励】两条入口都没能进入好友面板，任务终止")
                return False
        else:
            print("【好友奖励】已进入社交界面，等待 2 秒...")
            time.sleep(2)

    # 识别 yijianzengli / notyijianzengli
    yijianzengli_pos = find_center(YIJIANZENGLI, threshold=0.8)
    notyijianzengli_pos = find_center(NOTYIJIANZENGLI, threshold=0.8)

    if yijianzengli_pos:
        clicks = _collect_gifts()
        if clicks:
            print(f"【好友奖励】一键赠礼并收取共点击 {clicks} 次，结算弹窗已清理")
        else:
            print("【好友奖励】按钮在首次检查后就不可见，视为已处理")
    elif notyijianzengli_pos:
        print("【好友奖励】检测到 notyijianzengli（已赠礼/无需赠礼），跳过赠礼，直接进入退出流程")
    else:
        print("【好友奖励】未检测到 yijianzengli 或 notyijianzengli，任务终止")
        return False

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
    return True
