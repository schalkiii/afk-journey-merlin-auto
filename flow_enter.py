# F:\afkj\game-bot\flow_enter.py
"""进入游戏 / 返回主界面流程模块。

关键接口：
- flow_enter_game(): 从启动/挂机界面点击「开始」进入游戏主界面。
- flow_return_main(): 经收件箱返回主界面，供各任务结束后统一回到起点。
"""

from common import get_template_path, recover_to_main_interface, wait_and_click


def flow_return_main(max_tries=6):
    """经若干次返回操作回到游戏主界面（以主界面「玩法目录 wanfamulu」按钮可见为判定）。

    委托给 common.recover_to_main_interface，复用统一的兜底退出逻辑
    （点击空白处关闭 / tuichulibao / exitck / exit 逐层退出，必要时空白兜底），
    避免把游戏停留在子界面（如社交/好友界面、玩法目录）导致后续任务卡死。
    """
    return recover_to_main_interface(max_tries=max_tries)

tpl_start = get_template_path("start.png")

def flow_enter_game():
    # 进入游戏：只点击一次 start.png
    return wait_and_click(tpl_start, "start.png", 0.8)

if __name__ == "__main__":
    flow_enter_game()