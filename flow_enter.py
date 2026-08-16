# F:\afkj\game-bot\flow_enter.py
"""进入游戏 / 返回主界面流程模块。

关键接口：
- flow_enter_game(): 从启动/挂机界面点击「开始」进入游戏主界面。
- flow_return_main(): 经收件箱返回主界面，供各任务结束后统一回到起点。
"""

from common import wait_and_click, get_template_path, find_center, send_coord, click_blank_to_exit
import time


def flow_return_main(max_tries=6):
    """经若干次返回操作回到游戏主界面（以主界面「玩法目录 wanfamulu」按钮可见为判定）。

    依次尝试：点击 exit 返回上一层 / 点击「点击空白处关闭」关闭弹窗，
    直到检测到主界面或达到最大尝试次数。供各任务结束后统一回到起点，
    避免把游戏停留在子界面（如社交/好友界面、玩法目录）导致后续任务卡死。
    """
    tpl_wanfamulu = get_template_path("wanfamulu.png")
    tpl_exit = get_template_path("exit.png")
    tpl_close = get_template_path("dianjikongbaichuguanbi.png")
    for _ in range(max_tries):
        if find_center(tpl_wanfamulu, 0.8):
            return True
        pos = find_center(tpl_exit, 0.8)
        if pos:
            send_coord(pos[0], pos[1])
            time.sleep(1.5)
            continue
        pos = find_center(tpl_close, 0.8)
        if pos:
            send_coord(pos[0], pos[1])
            time.sleep(1.5)
            continue
        # 兜底：既无返回按钮也无「点击空白处关闭」时，点击屏幕空白处尝试退出弹窗
        click_blank_to_exit()
        time.sleep(1.0)
    return find_center(tpl_wanfamulu, 0.8) is not None

tpl_start = get_template_path("start.png")

def flow_enter_game():
    # 进入游戏：只点击一次 start.png
    if not wait_and_click(tpl_start, "start.png", 0.8):
        return False
    return True

if __name__ == "__main__":
    flow_enter_game()