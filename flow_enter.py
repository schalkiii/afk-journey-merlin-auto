# F:\afkj\game-bot\flow_enter.py
from common import wait_and_click, get_template_path

tpl_start = get_template_path("start.png")

def flow_enter_game():
    # 进入游戏：只点击一次 start.png
    if not wait_and_click(tpl_start, "start.png", 0.8):
        return False
    return True

if __name__ == "__main__":
    flow_enter_game()