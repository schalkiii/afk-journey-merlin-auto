# F:\afkj\game-bot\youyishangcheng.py
import os
import time
from common import wait_and_click, get_resource_path

# 模板路径
templates_dir = get_resource_path("templates")

def main():
    print("开始执行友谊商城任务...")
    
    # 1. 识别并点击youyishangdian
    youyishangdian_path = os.path.join(templates_dir, "youyishangdian.png")
    if not wait_and_click(youyishangdian_path, "youyishangdian"):
        print("未找到youyishangdian，任务终止")
        return
    time.sleep(2)
    
    # 2. 识别并点击dazhexinwu
    dazhexinwu_path = os.path.join(templates_dir, "dazhexinwu.png")
    if not wait_and_click(dazhexinwu_path, "dazhexinwu", timeout=5):
        print("未找到dazhexinwu，任务终止")
        return
    time.sleep(2)
    
    # 3. 识别并点击goumaidazhexinwu
    goumaidazhexinwu_path = os.path.join(templates_dir, "goumaidazhexinwu.png")
    if not wait_and_click(goumaidazhexinwu_path, "goumaidazhexinwu"):
        print("未找到goumaidazhexinwu，任务终止")
        return
    time.sleep(2)
    
    # 4. 识别并点击dianjikongbaichuguanbi
    dianjikongbaichuguanbi_path = os.path.join(templates_dir, "dianjikongbaichuguanbi.png")
    if not wait_and_click(dianjikongbaichuguanbi_path, "dianjikongbaichuguanbi"):
        print("未找到dianjikongbaichuguanbi，任务终止")
        return
    
    print("友谊商城任务执行完成！")

if __name__ == "__main__":
    main()
