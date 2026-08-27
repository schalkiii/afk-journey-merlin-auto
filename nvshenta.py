import random
import time

from common import (
    find_center_silent,
    get_template_path,
    screenshot_bgr,
    send_coord,
    try_auto_configure_lineup,
    wait_and_click,
)
from jiance import check_and_handle_libao


# 随机等待函数，2-3秒
def random_sleep():
    time.sleep(random.uniform(2.0, 3.0))

# === 模板路径 ===
tpl_wanfamulu = get_template_path("wanfamulu.png")
tpl_nvshenta = get_template_path("nvshenta.png")
tpl_nvshentiaozhan = get_template_path("nvshentiaozhan.png")
tpl_zhandou = get_template_path("zhandou.png")
tpl_nvshentaxiayiceng = get_template_path("nvshentaxiayiceng.png")
tpl_exitck = get_template_path("exitck.png")
tpl_exit = get_template_path("exit.png")
tpl_nvshentasaodang = get_template_path("nvshentasaodang.png")
tpl_nvshentasaodangmax = get_template_path("nvshentasaodangmax.png")
tpl_dianjikongbaichuguanbi = get_template_path("dianjikongbaichuguanbi.png")
tpl_nvshentahuiji = get_template_path("nvshentahuiji.png")
tpl_jingzhihuiji = get_template_path("jingzhihuiji.png")

# 一场战斗最长等待时间（秒）
MAX_BATTLE_TIME = 180

# 等待某张图出现
def wait_for_appearance(template_path, name, threshold=0.8, timeout=MAX_BATTLE_TIME, interval=0.5):
    """循环等待某张图出现，出现返回坐标，超时返回 None。"""
    start = time.time()
    attempt = 0
    while True:
        attempt += 1
        pos = find_center_silent(template_path, threshold)
        if pos:
            print(f"{name} 出现，第 {attempt} 次检测，坐标: {pos}")
            return pos

        elapsed = time.time() - start
        if elapsed > timeout:
            print(f"{name} 在 {timeout} 秒内未出现，放弃等待。")
            return None

        time.sleep(interval)

def do_saodang_and_exit():
    """
    功能：执行扫荡并退出女神塔（复用函数）
    
    流程：
    1. 点击 nvshentasaodang 扫荡
    2. 点击 nvshentasaodangmax 选择最大扫荡次数
    3. 点击 nvshentasaodang 确认扫荡
    4. 点击 dianjikongbaichuguanbi 关闭扫荡结果
    5. 点击 exit 退出女神塔
    6. 调用 jiance.py 检测礼包弹窗
    """
    
    # 1. 点击 nvshentasaodang 扫荡
    if not wait_and_click(tpl_nvshentasaodang, "nvshentasaodang", 0.8):
        print("点击 nvshentasaodang 失败")
        return False
    random_sleep()
    
    # 2. 点击 nvshentasaodangmax 选择最大扫荡次数
    # 先检测是否存在 nvshentasaodangmax
    pos_saodangmax = find_center_silent(tpl_nvshentasaodangmax, 0.8)
    if not pos_saodangmax:
        print("识别不到 nvshentasaodangmax，直接退出")
        # 直接点击 exitck 退出
        if not wait_and_click(tpl_exitck, "exit_final", 0.8):
            print("点击 exitck 退出女神塔失败")
            return False
        random_sleep()
        
        # 调用 jiance.py 检测礼包弹窗
        print("开始检测礼包弹窗...")
        check_and_handle_libao()
        print("礼包弹窗检测完成")
        
        return True
    
    if not wait_and_click(tpl_nvshentasaodangmax, "nvshentasaodangmax", 0.8):
        print("点击 nvshentasaodangmax 失败")
        return False
    random_sleep()
    
    # 3. 点击 nvshentasaodang 确认扫荡
    if not wait_and_click(tpl_nvshentasaodang, "nvshentasaodang_confirm", 0.8):
        print("点击 nvshentasaodang 确认失败")
        return False
    random_sleep()
    
    # 4. 点击 dianjikongbaichuguanbi 关闭扫荡结果
    if not wait_and_click(tpl_dianjikongbaichuguanbi, "dianjikongbaichuguanbi", 0.8):
        print("点击 dianjikongbaichuguanbi 失败")
        return False
    random_sleep()
    
    # 5. 点击 exit 退出女神塔
    if not wait_and_click(tpl_exitck, "exit_final", 0.8):
        print("点击 exitck 退出女神塔失败")
        return False
    random_sleep()
    
    # 6. 调用 jiance.py 检测礼包弹窗
    print("开始检测礼包弹窗...")
    check_and_handle_libao()
    print("礼包弹窗检测完成")
    
    return True


def flow_nvshenta(auto_configure_lineup=False):
    """
    功能：女神塔挑战
    
    入口：当前在游戏主界面。
    
    流程：
    1. 点击 wanfamulu 进入玩法目录
    2. 点击 nvshenta 进入女神塔界面
    3. 循环挑战：
       - 点击 nvshentiaozhan 挑战
       - 点击 zhandou 战斗
       - 如果识别到 nvshentaxiayiceng，点击进入下一层，继续挑战
       - 如果识别不到 nvshentaxiayiceng，挑战结束
    4. 点击 exit 退出到女神塔界面
    5. 点击 nvshentasaodang 扫荡
    6. 点击 nvshentasaodangmax 选择最大扫荡次数
    7. 点击 nvshentasaodang 确认扫荡
    8. 点击 dianjikongbaichuguanbi 关闭扫荡结果
    9. 点击 exit 退出女神塔
    10. 调用 jiance.py 检测礼包弹窗
    """
    
    # 1. 点击 wanfamulu 进入玩法目录
    if not wait_and_click(tpl_wanfamulu, "wanfamulu", 0.7, recover_threshold=20):
        print("点击 wanfamulu 失败")
        return False
    random_sleep()
    
    # 2. 点击 nvshenta 进入女神塔界面
    if not wait_and_click(tpl_nvshenta, "nvshenta", 0.8):
        print("点击 nvshenta 失败")
        return False
    random_sleep()
    
    # 2.5 检测当前界面状态：判断是挑战界面还是扫荡界面
    # 如果直接识别到扫荡按钮，说明已经通关
    pos_saodang = find_center_silent(tpl_nvshentasaodang, 0.8)
    if pos_saodang:
        print("检测到扫荡按钮，已通关")
        # 计算扫荡按钮下方的区域
        # 从扫荡按钮下方0像素开始，宽度为整个屏幕，高度为300像素
        screen_width = screenshot_bgr().shape[1]
        saodang_x, saodang_y = pos_saodang
        # 计算下方区域：从扫荡按钮下方0像素开始，宽度为整个屏幕，高度为300像素
        search_region = (0, saodang_y, screen_width, 300)
        print(f"在扫荡按钮下方区域 {search_region} 检测回祭标识...")
        
        # 优先检测 jingzhihuiji，识别到则直接退出
        pos_jingzhi = find_center_silent(tpl_jingzhihuiji, 0.8, region=search_region)
        if pos_jingzhi:
            print("检测到精致回祭标识，直接退出")
            if not wait_and_click(tpl_exitck, "exitck", 0.8):
                print("点击 exitck 失败")
                return False
            random_sleep()
            # 调用 jiance.py 检测礼包弹窗
            print("开始检测礼包弹窗...")
            check_and_handle_libao()
            print("礼包弹窗检测完成")
            return True
        # 检测 nvshentahuiji，识别到则执行扫荡
        pos_huiji = find_center_silent(tpl_nvshentahuiji, 0.8, region=search_region)
        if pos_huiji:
            print("检测到女神塔回祭标识，执行扫荡")
            return do_saodang_and_exit()
        else:
            print("未检测到任何回祭标识，直接退出")
            if not wait_and_click(tpl_exitck, "exitck", 0.55):
                print("点击 exitck 失败")
                return False
            random_sleep()
            # 调用 jiance.py 检测礼包弹窗
            print("开始检测礼包弹窗...")
            check_and_handle_libao()
            print("礼包弹窗检测完成")
            return True
    
    # 3. 循环挑战
    challenge_count = 0
    
    # 第一次挑战需要点击挑战按钮
    challenge_count += 1
    print(f"开始第 {challenge_count} 层挑战")
    
    # 点击 nvshentiaozhan 挑战
    if not wait_and_click(tpl_nvshentiaozhan, "nvshentiaozhan", 0.8):
        print("点击 nvshentiaozhan 失败")
        return False
    random_sleep()
    # 可选：挑战前尝试自动采用通关阵容（检测并点击 tongguanzhenrong / yijiancaiyong）
    if auto_configure_lineup:
        if try_auto_configure_lineup():
            print("【女神塔】已自动采用通关阵容。")
        else:
            print("【女神塔】未检测到通关阵容入口，跳过自动配置。")

    # 点击 zhandou 战斗
    if not wait_and_click(tpl_zhandou, "zhandou", 0.8):
        print("点击 zhandou 失败")
        return False
    random_sleep()
    
    # 定义战斗标记模板
    tpl_nvshenta_zhandou_biaoji = get_template_path("nvshentazhandoubiaoji.png")
    
    # 等待战斗结束：检测战斗标记消失
    print("等待战斗结束...")
    battle_end = False
    start_time = time.time()
    no_battle_time = 0
    
    while time.time() - start_time < 30:  # 最大等待30秒
        # 检测战斗标记
        pos_battle = find_center_silent(tpl_nvshenta_zhandou_biaoji, 0.8)
        if not pos_battle:
            # 未检测到战斗标记，累计时间
            no_battle_time += 0.5
            if no_battle_time >= 5:
                # 5秒内检测不到战斗标记，认为战斗结束
                print("5秒内未检测到战斗标记，开始检测下一层按钮...")
                pos_next = wait_for_appearance(tpl_nvshentaxiayiceng, "nvshentaxiayiceng", 0.8, timeout=10.0)
                battle_end = True
                break
        else:
            # 检测到战斗标记，重置计时
            no_battle_time = 0
        time.sleep(0.5)
    
    if not battle_end:
        print("战斗超时，未检测到战斗结束")
        pos_next = None
    
    if not pos_next:
        print("未检测到下一层按钮，挑战结束")
    
    # 后续循环直接点击战斗按钮
    while pos_next:
        challenge_count += 1
        print(f"开始第 {challenge_count} 层挑战")
        
        # 点击下一层
        send_coord(pos_next[0], pos_next[1])
        random_sleep()
        # 可选：挑战前尝试自动采用通关阵容（检测并点击 tongguanzhenrong / yijiancaiyong）
        if auto_configure_lineup:
            if try_auto_configure_lineup():
                print("【女神塔】已自动采用通关阵容。")
            else:
                print("【女神塔】未检测到通关阵容入口，跳过自动配置。")

        # 直接点击 zhandou 战斗
        if not wait_and_click(tpl_zhandou, "zhandou", 0.8):
            print("点击 zhandou 失败")
            break
        random_sleep()
        
        # 定义战斗标记模板
        tpl_nvshenta_zhandou_biaoji = get_template_path("nvshentazhandoubiaoji.png")
        
        # 等待战斗结束：检测战斗标记消失
        print("等待战斗结束...")
        battle_end = False
        start_time = time.time()
        no_battle_time = 0
        
        while time.time() - start_time < 30:  # 最大等待30秒
            # 检测战斗标记
            pos_battle = find_center_silent(tpl_nvshenta_zhandou_biaoji, 0.8)
            if not pos_battle:
                # 未检测到战斗标记，累计时间
                no_battle_time += 0.5
                if no_battle_time >= 5:
                    # 5秒内检测不到战斗标记，认为战斗结束
                    print("5秒内未检测到战斗标记，开始检测下一层按钮...")
                    pos_next = wait_for_appearance(tpl_nvshentaxiayiceng, "nvshentaxiayiceng", 0.8, timeout=10.0)
                    battle_end = True
                    break
            else:
                # 检测到战斗标记，重置计时
                no_battle_time = 0
            time.sleep(0.5)
        
        if not battle_end:
            print("战斗超时，未检测到战斗结束")
            pos_next = None
        
        if not pos_next:
            print("未检测到下一层按钮，挑战结束")
    
    print(f"总共挑战了 {challenge_count} 层")
    
    # 4. 点击 exit 退出到女神塔界面
    if not wait_and_click(tpl_exit, "exit", 0.8):
        print("点击 exit 失败")
        return False
    random_sleep()
    
    # 5-10. 执行扫荡并退出
    if not do_saodang_and_exit():
        return False
    
    print("女神塔流程结束")
    return True

if __name__ == "__main__":
    flow_nvshenta()
