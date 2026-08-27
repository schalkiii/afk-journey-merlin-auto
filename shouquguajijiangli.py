# F:\afkj\game-bot\shouquguajijiangli.py
import os
import time

from common import find_center, get_templates_dir, wait_and_click

# 模板路径
templates_dir = get_templates_dir()

# 配置参数
# 设置是否使用付费次数，默认只使用免费次数
USE_PAID_TIMES = False
# 设置最多使用的付费次数（0-2）
MAX_PAID_TIMES = 0

# 状态定义
STATE_FREE_3 = "shalou1"  # 还能免费买三次
STATE_FREE_2 = "shalou2"  # 还能免费买两次
STATE_FREE_1 = "shalou3"  # 还能免费买一次
STATE_FREE_END = "shalou4"  # 免费结束
STATE_PAID_1 = "shalou5"  # 付费了一次
STATE_PAID_2 = "shalou6"  # 付费了两次

# 状态映射到模板文件
state_templates = {
    STATE_FREE_3: os.path.join(templates_dir, "shalou1.png"),
    STATE_FREE_2: os.path.join(templates_dir, "shalou2.png"),
    STATE_FREE_1: os.path.join(templates_dir, "shalou3.png"),
    STATE_FREE_END: os.path.join(templates_dir, "shalou4.png"),
    STATE_PAID_1: os.path.join(templates_dir, "shalou5.png"),
    STATE_PAID_2: os.path.join(templates_dir, "shalou6.png")
}

# 其他模板路径
goumai50_path = os.path.join(templates_dir, "goumai50.png")
goumai100_path = os.path.join(templates_dir, "goumai100.png")
querengoumaimenpiao_path = os.path.join(templates_dir, "querengoumaimenpiao.png")

def check_current_state():
    """
    检查当前状态
    返回：当前状态，未找到返回 None
    优先检测高级状态（shalou6 -> shalou1），避免误判
    """
    # 按优先级排序：高级状态优先检测
    priority_order = [
        STATE_PAID_2,    # shalou6 - 付费了两次（最高优先级）
        STATE_PAID_1,    # shalou5 - 付费了一次
        STATE_FREE_END,  # shalou4 - 免费结束
        STATE_FREE_1,    # shalou3 - 还能免费买一次
        STATE_FREE_2,    # shalou2 - 还能免费买两次
        STATE_FREE_3,    # shalou1 - 还能免费买三次（最低优先级）
    ]
    
    for state in priority_order:
        template_path = state_templates[state]
        pos = find_center(template_path, threshold=0.7)
        if pos:
            print(f"当前状态: {state}")
            return state
    return None

def main(paid_times=0):
    print("开始执行收取挂机奖励任务...")
    
    # 设置付费次数
    global USE_PAID_TIMES, MAX_PAID_TIMES
    if paid_times > 0:
        USE_PAID_TIMES = True
        MAX_PAID_TIMES = paid_times
    else:
        USE_PAID_TIMES = False
        MAX_PAID_TIMES = 0
    
    print(f"付费购买次数设置: {MAX_PAID_TIMES}")
    
    # 1. 识别并点击wanfamulu
    wanfamulu_path = os.path.join(templates_dir, "wanfamulu.png")
    if not wait_and_click(wanfamulu_path, "wanfamulu", threshold=0.7, recover_threshold=20):
        print("未找到wanfamulu，任务终止")
        return
    time.sleep(2)
    
    # 2. 识别并点击guajiguanqia
    guajiguanqia_path = os.path.join(templates_dir, "guajiguanqia.png")
    if not wait_and_click(guajiguanqia_path, "guajiguanqia"):
        print("未找到guajiguanqia，任务终止")
        return
    time.sleep(2)
    
    # 3. 检查是否出现guajijiangli或shouhuojiangli
    guajijiangli_path = os.path.join(templates_dir, "guajijiangli.png")
    shouhuojiangli_path = os.path.join(templates_dir, "shouhuojiangli.png")
    
    # 导入 common 模块中的 find_center 函数
    from common import find_center
    
    # 等待 10 秒，检查是否出现 guajijiangli 或 shouhuojiangli
    start_time = time.time()
    found_any = False
    
    print("等待 guajijiangli 或 shouhuojiangli...")
    while time.time() - start_time < 10:
        # 检查 guajijiangli
        if find_center(guajijiangli_path, threshold=0.8):
            print("检测到 guajijiangli，点击...")
            if wait_and_click(guajijiangli_path, "guajijiangli"):
                print("点击 guajijiangli 成功")
                time.sleep(2)
                # 点击 guajijiangli 后，再点击 shouhuojiangli
                if wait_and_click(shouhuojiangli_path, "shouhuojiangli"):
                    print("点击 shouhuojiangli 成功")
                else:
                    print("未找到 shouhuojiangli")
                found_any = True
                break
        
        # 检查 shouhuojiangli
        if find_center(shouhuojiangli_path, threshold=0.8):
            print("检测到 shouhuojiangli，点击...")
            if wait_and_click(shouhuojiangli_path, "shouhuojiangli"):
                print("点击 shouhuojiangli 成功")
                found_any = True
                break
        
        time.sleep(0.5)  # 避免 CPU 占用过高
    
    if not found_any:
        print("10 秒内未检测到 guajijiangli 或 shouhuojiangli，跳过这两个步骤")
    
    time.sleep(2)
    
    # 4. 状态机处理shalou
    print("开始处理shalou状态...")
    paid_count = 0
    
    while True:
        current_state = check_current_state()
        
        if current_state is None:
            print("未检测到任何shalou状态，任务终止")
            break
        
        # 检查是否应该停止
        if current_state == STATE_FREE_END:
            print("免费次数已用完，停止购买")
            break
        
        if not USE_PAID_TIMES and current_state in [STATE_PAID_1, STATE_PAID_2]:
            print("已开始使用付费次数，但配置为不使用付费次数，停止购买")
            break
        
        if USE_PAID_TIMES and paid_count >= MAX_PAID_TIMES:
            print(f"已使用 {paid_count} 次付费次数，达到最大限制 {MAX_PAID_TIMES}，停止购买")
            break
        
        # 点击shalou
        print(f"当前状态: {current_state}，点击购买")
        shalou_path = state_templates[current_state]
        if not wait_and_click(shalou_path, current_state):
            print(f"点击 {current_state} 失败，任务终止")
            break
        
        # 等待界面刷新
        print("等待界面刷新...")
        time.sleep(3)
        
        # 识别 exit 并移动到其附近（不点击），避免鼠标阻挡接下来的识别
        print("识别 exit 并移动鼠标到其附近...")
        exit_path = os.path.join(templates_dir, "exit.png")
        from common import find_center, send_coord
        exit_pos = find_center(exit_path, threshold=0.8)
        if exit_pos:
            # 计算偏移位置，避免点击到 exit 按钮
            move_pos = (exit_pos[0] + 50, exit_pos[1] )  # 偏移50像素
            print(f"找到 exit 位置: {exit_pos}，移动鼠标到: {move_pos}")
            # 使用 send_coord 函数移动鼠标到偏移位置
            send_coord(move_pos[0], move_pos[1])
        else:
            print("未找到 exit，跳过鼠标移动")
        
        # 检查是否出现goumai50或goumai100
        if current_state == STATE_FREE_END:  # shalou4
            # 检查是否出现goumai50
            print("检查是否出现goumai50...")
            time.sleep(1)
            if find_center(goumai50_path, threshold=0.7):
                print("检测到goumai50，点击querengoumaimenpiao")
                if not wait_and_click(querengoumaimenpiao_path, "querengoumaimenpiao"):
                    print("点击querengoumaimenpiao失败，任务终止")
                    break
                time.sleep(2)
        elif current_state == STATE_PAID_1:  # shalou5
            # 检查是否出现goumai100
            print("检查是否出现goumai100...")
            time.sleep(1)
            if find_center(goumai100_path, threshold=0.8):
                print("检测到goumai100，点击querengoumaimenpiao")
                if not wait_and_click(querengoumaimenpiao_path, "querengoumaimenpiao"):
                    print("点击querengoumaimenpiao失败，任务终止")
                    break
                time.sleep(2)
        
        # 更新付费次数计数
        if current_state in [STATE_FREE_END, STATE_PAID_1]:
            paid_count += 1
        
        # 等待状态变化
        time.sleep(2)
    
    # 点击exit退出
    exit_path = os.path.join(templates_dir, "exit.png")
    if not wait_and_click(exit_path, "exit"):
        print("未找到exit，退出失败")
    else:
        print("点击exit退出成功")
    
    print("收取挂机奖励任务执行完成！")

if __name__ == "__main__":
    main()
