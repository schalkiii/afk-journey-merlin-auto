# F:\afkj\game-bot\youjian.py
import os
import time
from common import wait_and_click, find_center, get_resource_path

# 模板路径
templates_dir = get_resource_path("templates")

def main():
    print("开始执行邮件任务...")
    
    # 1. 识别并点击caidan
    caidan_path = os.path.join(templates_dir, "caidan.png")
    if not wait_and_click(caidan_path, "caidan"):
        print("未找到caidan，任务终止")
        return
    time.sleep(2)
    
    # 2. 识别并点击youjian
    youjian_path = os.path.join(templates_dir, "youjian.png")
    if not wait_and_click(youjian_path, "youjian"):
        print("未找到youjian，任务终止")
        return
    time.sleep(2)
    
    # 3. 检查是 yueduquanbu 还是 notyueduquanbu
    yueduquanbu_path = os.path.join(templates_dir, "yueduquanbu.png")
    notyueduquanbu_path = os.path.join(templates_dir, "notyueduquanbu.png")
    
    # 检查是否存在 yueduquanbu
    yueduquanbu_pos = find_center(yueduquanbu_path, threshold=0.8)
    # 检查是否存在 notyueduquanbu
    notyueduquanbu_pos = find_center(notyueduquanbu_path, threshold=0.8)
    
    if notyueduquanbu_pos:
        print("检测到 notyueduquanbu，直接退出")
        # 直接跳到执行两次 exit 的位置
    elif yueduquanbu_pos:
        print("检测到 yueduquanbu，继续执行")
        # 3. 识别并点击yueduquanbu
        if not wait_and_click(yueduquanbu_path, "yueduquanbu"):
            print("未找到yueduquanbu，任务终止")
            return
        time.sleep(2)
        
        # 4. 识别并点击dianjikongbaichuguanbi
        dianjikongbaichuguanbi_path = os.path.join(templates_dir, "dianjikongbaichuguanbi.png")
        if not wait_and_click(dianjikongbaichuguanbi_path, "dianjikongbaichuguanbi"):
            print("未找到dianjikongbaichuguanbi，任务终止")
            return
        time.sleep(2)
    else:
        print("未检测到 yueduquanbu 或 notyueduquanbu，任务终止")
        return
    
    # 5. 点击exit
    exit_path = os.path.join(templates_dir, "exit.png")
    if not wait_and_click(exit_path, "exit"):
        print("未找到exit，任务终止")
        return
    time.sleep(2)
    
    # 6. 再次点击exit
    if not wait_and_click(exit_path, "exit"):
        print("未找到exit，任务终止")
        return
    
    print("邮件任务执行完成！")

if __name__ == "__main__":
    main()
