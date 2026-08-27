# F:\afkj\game-bot\shangcheng.py
import os
import time

import youyishangcheng
from common import get_templates_dir, wait_and_click

# 模板路径
templates_dir = get_templates_dir()

def main():
    print("开始执行商城任务...")
    
    # 1. 识别并点击shenmiwu
    shenmiwu_path = os.path.join(templates_dir, "shenmiwu.png")
    if not wait_and_click(shenmiwu_path, "shenmiwu"):
        print("未找到shenmiwu，任务终止")
        return
    time.sleep(2)
    
    # 2. 识别并点击shangdian
    shangdian_path = os.path.join(templates_dir, "shangdian.png")
    if not wait_and_click(shangdian_path, "shangdian"):
        print("未找到shangdian，任务终止")
        return
    time.sleep(2)
    
    # 3. 调用youyishangcheng
    print("开始调用youyishangcheng...")
    youyishangcheng.main()
    
    # 4. 点击exitck退出
    exitck_path = os.path.join(templates_dir, "exitck.png")
    if not wait_and_click(exitck_path, "exitck"):
        print("未找到exitck，退出失败")
    else:
        print("点击exitck退出成功")
    
    print("商城任务执行完成！")

if __name__ == "__main__":
    main()
