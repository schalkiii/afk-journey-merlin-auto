import time

from common import (
    BOTTOM_BAR_CLIENT_REGION,
    find_center_silent,
    get_template_path,
    random_sleep,
    recover_to_main_interface,
    send_coord,
    wait_and_click,
)

# 模板路径
tpl_wanfamulu = get_template_path("wanfamulu.png")
tpl_pata = get_template_path("pata.png")
tpl_yaoguangzhita = get_template_path("yaoguangzhita.png")
tpl_ziranzhita = get_template_path("ziranzhita.png")
tpl_manxuezhita = get_template_path("manxuezhita.png")
tpl_wanglingzhita = get_template_path("wanglingzhita.png")
tpl_exit = get_template_path("exit.png")

# 塔的顺序
TOWER_ORDER = [
    ("yaoguangzhita", tpl_yaoguangzhita),
    ("ziranzhita", tpl_ziranzhita),
    ("manxuezhita", tpl_manxuezhita),
    ("wanglingzhita", tpl_wanglingzhita),
]

def flow_pata():
    """
    爬塔总协调脚本
    
    流程：
    1. 识别并点击 wanfamulu 进入玩法目录界面
    2. 识别并点击 pata 进入爬塔选择界面
    3. 按照顺序依次点击：yaoguangzhita, ziranzhita, manxuezhita, wanglingzhita
    4. 每次点击后调用 flow_tower.py
    5. flow_tower.py 结束后自动返回 pata 界面
    6. 继续按顺序点击下一个塔
    7. 所有塔都完成后，点击 exit
    8. 调用 jiance.py 检测礼包
    9. 结束脚本
    """
    # 0. 先回到主界面：任务可能从上个任务的子页面开始，子页底部同样有 wanfamulu 图标，
    # 直接点击会被误判成功，随后在子页里找不到 pata。
    # 恢复失败不改变原有失败语义，仍按原流程继续尝试进入玩法目录。
    if recover_to_main_interface():
        print("已回到主界面，开始进入玩法目录。")
    else:
        print("恢复主界面失败，继续尝试进入玩法目录。")

    # 1. 点击 wanfamulu 进入玩法目录界面
    if not wait_and_click(tpl_wanfamulu, "wanfamulu", 0.7, recover_threshold=20,
                          client_region=BOTTOM_BAR_CLIENT_REGION):
        print("点击 wanfamulu 进入玩法目录界面失败。")
        return False
    random_sleep()

    # 2. 点击 pata 进入爬塔选择界面
    if not wait_and_click(tpl_pata, "pata", 0.8):
        print("点击 pata 进入爬塔选择界面失败。")
        return False
    random_sleep()

    # 3. 按照顺序依次点击各个塔
    for tower_name, tower_tpl in TOWER_ORDER:
        print(f"\n========== 开始处理 {tower_name} ==========")
        
        # 检测该塔是否存在
        pos = find_center_silent(tower_tpl, threshold=0.9)
        if pos is None:
            print(f"{tower_name} 未检测到，跳过。")
            continue
        
        print(f"{tower_name} 检测到，位置: {pos}")
        
        # 点击进入该塔
        send_coord(pos[0], pos[1])
        random_sleep()
        
        # 调用 flow_tower.py
        print(f"调用 flow_tower.py 处理 {tower_name}...")
        try:
            from flow_tower import flow_tower
            result = flow_tower()
            if result is None:
                print(f"{tower_name} 处理完成")
            else:
                print(f"{tower_name} 处理返回: {result}")
        except Exception as e:
            print(f"调用 flow_tower.py 时出错: {e}")
        
        # flow_tower.py 结束后会自动返回到 pata 界面
        # 等待一下确保界面切换完成
        time.sleep(2.0)
        
        print(f"========== {tower_name} 处理完成 ==========\n")

    # 4. 所有塔都完成后，点击 exit
    print("\n所有塔处理完成，点击 exit 退出...")
    if not wait_and_click(tpl_exit, "exit", 0.8):
        print("点击 exit 失败。")
        return False
    random_sleep()

    # 5. 调用 jiance.py 检测礼包
    print("调用 jiance.py 检测礼包...")
    try:
        from jiance import check_and_handle_libao
        check_and_handle_libao(timeout=10.0, interval=0.5)
        print("礼包检测完成")
    except Exception as e:
        print(f"调用 jiance.py 时出错: {e}")

    print("\npata.py 脚本执行完成")
    return True


def main():
    """主函数，供其他脚本调用"""
    return flow_pata()

if __name__ == "__main__":
    main()
