# F:\afkj\game-bot\start.py
import os
import time
from common import wait_and_click, find_center, get_templates_dir

# 模板路径
templates_dir = get_templates_dir()

def main():
    print("开始执行启动任务...")
    
    # 定义模板路径
    start_path = os.path.join(templates_dir, "start.png")
    yuekajiangli_path = os.path.join(templates_dir, "yuekajiangli.png")
    libao_path = os.path.join(templates_dir, "libao.png")
    tuichulibao_path = os.path.join(templates_dir, "tuichulibao.png")
    
    # 1. 尝试点击start，最多等待60秒
    print("60秒内检测start...")
    start_time = time.time()
    start_clicked = False
    
    while time.time() - start_time < 60:
        # 检测是否直接出现了yuekajiangli或libao
        yuekajiangli_pos = find_center(yuekajiangli_path, threshold=0.8)
        libao_pos = find_center(libao_path, threshold=0.8)
        
        if yuekajiangli_pos or libao_pos:
            print("检测到yuekajiangli或libao，认为start已经被点过了，跳过")
            start_clicked = True
            break
        
        # 检测start
        start_pos = find_center(start_path, threshold=0.8)
        if start_pos:
            print("检测到start，点击")
            if wait_and_click(start_path, "start"):
                start_clicked = True
                print("点击start成功")
                time.sleep(2)
            break
        
        time.sleep(0.5)
    
    if not start_clicked:
        print("60秒内未检测到start，跳过")
    
    # 2. 循环检测yuekajiangli和libao，谁先出现就点谁
    print("开始检测yuekajiangli和libao...")
    last_detection_time = time.time()
    
    while True:
        # 检测yuekajiangli和libao
        yuekajiangli_pos = find_center(yuekajiangli_path, threshold=0.8)
        libao_pos = find_center(libao_path, threshold=0.8)
        
        if yuekajiangli_pos:
            print("检测到yuekajiangli，点击")
            if wait_and_click(yuekajiangli_path, "yuekajiangli"):
                print("点击yuekajiangli成功")
                time.sleep(2)
            last_detection_time = time.time()
        elif libao_pos:
            print("检测到libao，点击tuichulibao")
            if wait_and_click(tuichulibao_path, "tuichulibao"):
                print("点击tuichulibao成功")
                time.sleep(2)
            last_detection_time = time.time()
        else:
            # 检查是否连续30秒未检测到任何元素
            if time.time() - last_detection_time >= 30:
                print("连续30秒未检测到yuekajiangli和libao，任务结束")
                break
        
        time.sleep(0.5)
    
    print("启动任务执行完成！")

if __name__ == "__main__":
    main()
