# F:\afkj\game-bot\meirirenwu.py
import os
import time
from common import wait_and_click, find_center, get_templates_dir

# 模板路径
templates_dir = get_templates_dir()

def main():
    print("开始执行每日任务...")
    
    # 1. 识别并点击caidan
    caidan_path = os.path.join(templates_dir, "caidan.png")
    if not wait_and_click(caidan_path, "caidan"):
        print("未找到caidan，任务终止")
        return
    time.sleep(2)
    
    # 2. 识别并点击renwu
    renwu_path = os.path.join(templates_dir, "renwu.png")
    if not wait_and_click(renwu_path, "renwu"):
        print("未找到renwu，任务终止")
        return
    time.sleep(2)
    
    # 3. 点击richangrenwu
    richangrenwu_path = os.path.join(templates_dir, "richangrenwu.png")
    if not wait_and_click(richangrenwu_path, "richangrenwu", threshold=0.7):
        print("未找到richangrenwu，任务终止")
        return
    time.sleep(2)
    
    # 4. 3秒内识别yijianlingqu，如果识别不到就跳过步骤4、5、6
    print("3秒内检测yijianlingqu...")
    yijianlingqu_path = os.path.join(templates_dir, "yijianlingqu.png")
    start_time = time.time()
    yijianlingqu_found = False
    
    while time.time() - start_time < 3:
        pos = find_center(yijianlingqu_path, threshold=0.8)
        if pos:
            print("检测到yijianlingqu，点击")
            if wait_and_click(yijianlingqu_path, "yijianlingqu"):
                yijianlingqu_found = True
                time.sleep(2)
                
                # 5. 点击meirirenwujiangli
                meirirenwujiangli_path = os.path.join(templates_dir, "meirirenwujiangli.png")
                if not wait_and_click(meirirenwujiangli_path, "meirirenwujiangli"):
                    print("未找到meirirenwujiangli，跳过")
                    break
                
                time.sleep(2)
                
                # 6. 点击dianjikongbaichuguanbi
                dianjikongbaichuguanbi_path = os.path.join(templates_dir, "dianjikongbaichuguanbi.png")
                if not wait_and_click(dianjikongbaichuguanbi_path, "dianjikongbaichuguanbi"):
                    print("未找到dianjikongbaichuguanbi，跳过")
            break
        time.sleep(0.5)
    
    if not yijianlingqu_found:
        print("3秒内未检测到yijianlingqu，跳过步骤4、5、6，直接执行步骤7")
    
    # 7. 点击gonghuirenwu
    gonghuirenwu_path = os.path.join(templates_dir, "gonghuirenwu.png")
    if not wait_and_click(gonghuirenwu_path, "gonghuirenwu"):
        print("未找到gonghuirenwu，任务终止")
        return
    time.sleep(2)
    
    # 8. 3秒内识别yijianlingqu，如果识别不到就跳过
    print("3秒内检测yijianlingqu...")
    start_time = time.time()
    yijianlingqu_found = False
    
    while time.time() - start_time < 3:
        pos = find_center(yijianlingqu_path, threshold=0.8)
        if pos:
            print("检测到yijianlingqu，点击")
            if wait_and_click(yijianlingqu_path, "yijianlingqu"):
                yijianlingqu_found = True
                time.sleep(2)
            break
        time.sleep(0.5)
    
    if yijianlingqu_found:
        # 9. 点击dianjikongbaichuguanbi
        if not wait_and_click(dianjikongbaichuguanbi_path, "dianjikongbaichuguanbi"):
            print("未找到dianjikongbaichuguanbi，跳过")
        time.sleep(2)
    else:
        print("3秒内未检测到yijianlingqu，直接退出")
    
    # 10. 点击exitck
    exitck_path = os.path.join(templates_dir, "exitck.png")
    if not wait_and_click(exitck_path, "exitck"):
        print("未找到exitck，任务终止")
        return
    time.sleep(2)
    
    # 11. 点击exit
    exit_path = os.path.join(templates_dir, "exit.png")
    if not wait_and_click(exit_path, "exit"):
        print("未找到exit，任务终止")
        return
    
    print("每日任务执行完成！")

if __name__ == "__main__":
    main()
