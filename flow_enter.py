# F:\afkj\game-bot\flow_enter.py
"""进入游戏 / 返回主界面流程模块。

关键接口：
- flow_enter_game(): 从启动/挂机界面点击「开始」进入游戏主界面。
- flow_return_main(): 经收件箱返回主界面，供各任务结束后统一回到起点。
"""

from common import wait_and_click, get_template_path

tpl_start = get_template_path("start.png")

def flow_enter_game():
    # 进入游戏：只点击一次 start.png
    if not wait_and_click(tpl_start, "start.png", 0.8):
        return False
    return True

if __name__ == "__main__":
    flow_enter_game()