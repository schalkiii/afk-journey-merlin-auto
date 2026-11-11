"""邮件领取：等待邮件面板加载、执行一键领取并关闭结算弹窗。

入口 `main()`，被 GUI「邮件」任务分发；依赖 `common` 的模板匹配与等待原语。
"""

import os
import time

from common import check_stop, find_center, get_templates_dir, wait_and_click

# 模板路径
templates_dir = get_templates_dir()
yueduquanbu_path = os.path.join(templates_dir, "yueduquanbu.png")
notyueduquanbu_path = os.path.join(templates_dir, "notyueduquanbu.png")

# 邮件面板轮询参数：点击 youjian 后面板可能有加载/动画延迟，单次判定容易漏按钮
PANEL_LOAD_TIMEOUT = 5.0
PANEL_POLL_INTERVAL = 0.5


def _wait_mail_state(timeout=PANEL_LOAD_TIMEOUT, interval=PANEL_POLL_INTERVAL):
    """轮询等待邮件面板的「一键已读」/「未读」按钮出现。

    点击 youjian 后面板有加载与动画延迟，模板单次检测容易漏判（实测连续 19 次未命中、
    6.6 秒才出现），因此按 interval 轮询到 timeout。命中任一按钮立即返回
    ("read"|"unread", 坐标)；超时返回 (None, None)。
    """
    deadline = time.time() + timeout
    while True:
        # find_center 本身不做停止检查，这里手动检查，保证长轮询能被 F9 中断
        check_stop()
        pos = find_center(yueduquanbu_path, threshold=0.8)
        if pos:
            return "read", pos
        pos = find_center(notyueduquanbu_path, threshold=0.8)
        if pos:
            return "unread", pos
        if time.time() >= deadline:
            return None, None
        time.sleep(interval)


def main():
    print("开始执行邮件任务...")
    
    # 1. 识别并点击caidan
    caidan_path = os.path.join(templates_dir, "caidan.png")
    if not wait_and_click(caidan_path, "caidan"):
        print("未找到caidan，任务终止")
        return False
    time.sleep(2)
    
    # 2. 识别并点击youjian
    youjian_path = os.path.join(templates_dir, "youjian.png")
    if not wait_and_click(youjian_path, "youjian"):
        print("未找到youjian，任务终止")
        return False
    time.sleep(2)
    
    # 3. 轮询等待面板加载出已读/未读按钮（单次立即判断会在加载慢时误判失败）
    panel_state, _panel_pos = _wait_mail_state()
    if panel_state is None:
        print("5 秒内未看到已读/未读按钮，任务终止")
        return False

    if panel_state == "unread":
        print("检测到 notyueduquanbu，直接退出")
        # 直接跳到执行两次 exit 的位置
    else:
        print("检测到 yueduquanbu，继续执行")
        # 3. 识别并点击yueduquanbu
        if not wait_and_click(yueduquanbu_path, "yueduquanbu"):
            print("未找到yueduquanbu，任务终止")
            return False
        time.sleep(2)
        
        # 4. 识别并点击dianjikongbaichuguanbi
        dianjikongbaichuguanbi_path = os.path.join(templates_dir, "dianjikongbaichuguanbi.png")
        if not wait_and_click(dianjikongbaichuguanbi_path, "dianjikongbaichuguanbi"):
            print("未找到dianjikongbaichuguanbi，任务终止")
            return False
        time.sleep(2)
    
    # 5. 点击exit
    exit_path = os.path.join(templates_dir, "exit.png")
    if not wait_and_click(exit_path, "exit"):
        print("未找到exit，任务终止")
        return False
    time.sleep(2)
    
    # 6. 再次点击exit
    if not wait_and_click(exit_path, "exit"):
        print("未找到exit，任务终止")
        return False
    
    print("邮件任务执行完成！")
    return True

if __name__ == "__main__":
    main()
