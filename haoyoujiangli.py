"""好友奖励流程模块。

从主界面进入 菜单 → 社交 → 一键赠礼，清理结算弹窗后经 flow_return_main 返回主界面。
目的：领取好友赠送的奖励（不含自身资源消耗）。入口 main() 由 GUI「挂机奖励」脚本调用。
"""

import os
import time
from common import wait_and_click, find_center, get_templates_dir, send_coord
from flow_enter import flow_return_main

# 模板路径
templates_dir = get_templates_dir()

CLOSE_POPUP = os.path.join(templates_dir, "dianjikongbaichuguanbi.png")


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


def main():
    print("【好友奖励】开始执行好友奖励任务...")

    # 识别并点击菜单
    caidan_path = os.path.join(templates_dir, "caidan.png")
    if not wait_and_click(caidan_path, "菜单"):
        print("【好友奖励】未找到菜单(caidan)，任务终止")
        return
    print("【好友奖励】已进入菜单，等待 2 秒...")
    time.sleep(2)

    # 识别并点击社交
    shejiao_path = os.path.join(templates_dir, "shejiao.png")
    if not wait_and_click(shejiao_path, "社交"):
        print("【好友奖励】未找到社交(shejiao)，任务终止")
        return
    print("【好友奖励】已进入社交界面，等待 2 秒...")
    time.sleep(2)

    # 识别 yijianzengli / notyijianzengli
    yijianzengli_path = os.path.join(templates_dir, "yijianzengli.png")
    notyijianzengli_path = os.path.join(templates_dir, "notyijianzengli.png")

    yijianzengli_pos = find_center(yijianzengli_path, threshold=0.8)
    notyijianzengli_pos = find_center(notyijianzengli_path, threshold=0.8)

    if notyijianzengli_pos:
        print("【好友奖励】检测到 notyijianzengli（已赠礼/无需赠礼），跳过赠礼，直接进入退出流程")
    elif yijianzengli_pos:
        print("【好友奖励】检测到 yijianzengli，点击一键赠礼")
        if not wait_and_click(yijianzengli_path, "一键赠礼"):
            print("【好友奖励】未找到一键赠礼(yijianzengli)，任务终止")
            return
        time.sleep(2)
        print("【好友奖励】一键赠礼完成，清理结算弹窗...")
        _close_popups()
    else:
        print("【好友奖励】未检测到 yijianzengli 或 notyijianzengli，任务终止")
        return

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
