# F:\afkj\game-bot\start.py
"""启动任务模块：登录游戏并清理开局弹窗。

被「运行登录」功能调用。逻辑分两阶段：
1. 等待开始界面点击 start 进入游戏；若游戏已越过开始界面（直接出现月卡/礼包）则跳过。
2. 循环处理月卡奖励与礼包弹窗，二者出现任一即点击对应按钮，直到连续一段时间无弹窗
   （认为启动完成）才结束，避免无限空轮询。
"""

import os
import time

from common import find_center, get_resource_path, wait_and_click

# 模板图片目录（兼容打包后的 exe）
templates_dir = get_resource_path("templates")

# 各阶段等待/空闲阈值（秒）
START_WAIT_TIMEOUT = 60      # 开始界面最长等待时间
POPUP_IDLE_TIMEOUT = 30       # 连续无弹窗多久即判定启动完成


def _wait_for_start(start_path, yuekajiangli_path, libao_path, timeout=START_WAIT_TIMEOUT):
    """等待开始界面并点击 start 进入游戏。

    若游戏已越过开始界面（月卡/礼包直接出现），视为 start 已被点过，直接跳过。
    返回 True 表示已处理（点击或跳过），False 表示超时未出现。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        # 游戏已越过开始界面：月卡/礼包直接出现，无需再点 start
        if find_center(yuekajiangli_path, 0.8) or find_center(libao_path, 0.8):
            print("检测到月卡/礼包界面，视为已开始，跳过 start")
            return True
        if find_center(start_path, 0.8):
            print("检测到 start，点击进入")
            wait_and_click(start_path, "start")
            time.sleep(2)
            return True
        time.sleep(0.5)
    return False


def _dismiss_popups(yuekajiangli_path, libao_path, tuichulibao_path, idle_timeout=POPUP_IDLE_TIMEOUT):
    """循环点击月卡奖励与礼包弹窗，直到连续 idle_timeout 秒无弹窗。"""
    last_seen = time.time()
    while True:
        if find_center(yuekajiangli_path, 0.8):
            wait_and_click(yuekajiangli_path, "yuekajiangli")
            time.sleep(2)
            last_seen = time.time()
        elif find_center(libao_path, 0.8):
            # 礼包弹窗的关闭按钮是 tuichulibao 模板，而非 libao 本身
            wait_and_click(tuichulibao_path, "tuichulibao")
            time.sleep(2)
            last_seen = time.time()
        elif time.time() - last_seen >= idle_timeout:
            print(f"连续 {idle_timeout} 秒未检测到弹窗，启动完成")
            break
        time.sleep(0.5)


def main():
    """启动任务入口：登录并清理开局弹窗。"""
    print("开始执行启动任务...")
    start_path = os.path.join(templates_dir, "start.png")
    yuekajiangli_path = os.path.join(templates_dir, "yuekajiangli.png")
    libao_path = os.path.join(templates_dir, "libao.png")
    tuichulibao_path = os.path.join(templates_dir, "tuichulibao.png")

    if not _wait_for_start(start_path, yuekajiangli_path, libao_path):
        print("60 秒内未检测到开始界面，跳过启动流程")

    _dismiss_popups(yuekajiangli_path, libao_path, tuichulibao_path)
    print("启动任务执行完成！")


if __name__ == "__main__":
    main()
