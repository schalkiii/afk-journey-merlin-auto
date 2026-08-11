# F:\afkj\game-bot\haoyoujiangli.py
import os
import time
from common import wait_and_click, find_center, get_templates_dir

# 模板路径
templates_dir = get_templates_dir()

def main():
    print("开始执行好友奖励任务...")
    
    # 识别并点击菜单
    caidan_path = os.path.join(templates_dir, "caidan.png")
    if not wait_and_click(caidan_path, "菜单"):
        print("未找到菜单，任务终止")
        return
    time.sleep(2)
    
    # 识别并点击社交
    shejiao_path = os.path.join(templates_dir, "shejiao.png")
    if not wait_and_click(shejiao_path, "社交"):
        print("未找到社交，任务终止")
        return
    time.sleep(2)
    
    # 检查是 yijianzengli 还是 notyijianzengli
    yijianzengli_path = os.path.join(templates_dir, "yijianzengli.png")
    notyijianzengli_path = os.path.join(templates_dir, "notyijianzengli.png")
    
    # 检查是否存在 yijianzengli
    yijianzengli_pos = find_center(yijianzengli_path, threshold=0.8)
    # 检查是否存在 notyijianzengli
    notyijianzengli_pos = find_center(notyijianzengli_path, threshold=0.8)
    
    if notyijianzengli_pos:
        print("检测到 notyijianzengli，直接跳到点击 exitck")
        # 直接跳到执行点击 exitck，再点击 exit
    elif yijianzengli_pos:
        print("检测到 yijianzengli，继续执行")
        # 识别并点击一键赠礼
        if not wait_and_click(yijianzengli_path, "一键赠礼"):
            print("未找到一键赠礼，任务终止")
            return
        time.sleep(2)
        
        # 识别并点击点击空白处关闭
        dianjikongbaichuguanbi_path = os.path.join(templates_dir, "dianjikongbaichuguanbi.png")
        if not wait_and_click(dianjikongbaichuguanbi_path, "点击空白处关闭"):
            print("未找到点击空白处关闭，任务终止")
            return
        time.sleep(2)
    else:
        print("未检测到 yijianzengli 或 notyijianzengli，任务终止")
        return
    
    # 识别并点击exitck
    exitck_path = os.path.join(templates_dir, "exitck.png")
    if not wait_and_click(exitck_path, "exitck"):
        print("未找到exitck，任务终止")
        return
    time.sleep(2)
    
    # 识别并点击exit
    exit_path = os.path.join(templates_dir, "exit.png")
    if not wait_and_click(exit_path, "exit"):
        print("未找到exit，任务终止")
        return
    
    print("好友奖励任务执行完成！")

if __name__ == "__main__":
    main()
