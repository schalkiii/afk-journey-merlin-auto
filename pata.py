"""爬塔任务入口：按 `TOWER_ORDER` 逐塔分发到 `flow_tower`，并处理塔内礼包。

被 GUI「爬塔」任务分发，入口 `main()`；单塔异常只跳过该塔，不中断整条任务。
"""

import time

from common import (
    click_and_confirm,
    find_center_silent,
    get_template_path,
    is_loading_screen,
    log,
    open_wanfamulu,
    random_sleep,
    recover_to_main_interface,
    scroll_in_client_region,
    wait_and_click,
)

# 模板路径
tpl_wanfamulu = get_template_path("wanfamulu.png")
tpl_pata = get_template_path("pata.png")
tpl_patatiaozhan = get_template_path("patatiaozhan.png")
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


def _left_catalog_page():
    """已离开玩法目录：塔选择页与塔内页都不再有「玩法目录」标题。

    加载中画面同样没有标题，所以加载中直接判 False，等加载结束再确认——
    否则「点了没反应」和「正在加载」都会被误当成「已经进去了」。
    """
    if is_loading_screen():
        return False
    return find_center_silent(tpl_wanfamulu, 0.7) is None


def _in_tower_page():
    """已在塔内部：塔内独有的「爬塔挑战」按钮出现。

    2026-11-11 实机：进入塔曾用 `_left_catalog_page` 做确认，但**塔选择页同样没有**
    「玩法目录」标题，于是「点塔卡片被吞、仍停在选择页」也算通过，flow_tower 随后在
    选择页上找不到「爬塔挑战」，15 秒后误判「已经推完」并去点 exit 退出。
    塔内必然有「挑战」按钮（能点到某张塔卡片，说明该塔状态是「出发」= 有可挑战关卡），
    故选它作为判据：找不到就是没进去，由 click_and_confirm 补点。
    """
    if is_loading_screen():
        return False
    return find_center_silent(tpl_patatiaozhan, 0.9) is not None



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

    # 1. 点击 wanfamulu 进入玩法目录界面（用面板标题自证，首次点击被吞时补点）
    if not open_wanfamulu(threshold=0.7, timeout=8):
        print("点击 wanfamulu 进入玩法目录界面失败。")
        return False
    random_sleep()

    # 2. 找「天穹试炼」卡片并点击。常规玩法页卡片列表可滚动，该卡片在首屏下方、
    # 需下滑才看得到（2026-11-08 用户更正：不是活动下线）。旧的固定点位兜底会点到
    # 相邻卡片（女神试炼/巅峰竞技场），不可用；改为滚动列表后重试模板查找。
    card_pos = find_center_silent(tpl_pata, 0.8, timeout=3.0)
    # 2026-11-10 实机：一次滚两下会「滚过头」——现场截图里天穹试炼标题被推到列表顶部
    # 边缘、模板匹配不到。改为逐次下滑、每滑一次就检查一次。
    for attempt in range(1, 4):
        if card_pos is not None:
            break
        log(f"首屏未找到「天穹试炼」卡片，第 {attempt} 次下滑列表后再找。")
        scroll_in_client_region("down", times=1)
        card_pos = find_center_silent(tpl_pata, 0.8, timeout=2.0)
    if card_pos is None:
        log("滚动后仍未找到「天穹试炼」卡片，跳过爬塔。")
        return False
    # 点击后必须确认离开了玩法目录：2026-11-10 实机里这一下被吞掉，脚本却当成已进入，
    # 结果在目录页上找不到「爬塔挑战」，进而误判「已经推完」并去点 exit。
    if not click_and_confirm(tpl_pata, "天穹试炼(爬塔入口)", _left_catalog_page,
                             attempts=2, find_timeout=2.0, confirm_timeout=8.0):
        log("点击「天穹试炼」后仍停在玩法目录，跳过爬塔。")
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
        
        # 点击进入该塔，并确认真的进去了；没进去就不要调 flow_tower，
        # 否则它会在塔选择页里找「爬塔挑战」失败并误判成「已经推完」。
        if not click_and_confirm(tower_tpl, f"{tower_name}(进入塔)", _in_tower_page,
                                 attempts=2, threshold=0.9, find_timeout=1.0,
                                 confirm_timeout=10.0):
            print(f"{tower_name} 点击后未进入塔内，跳过该塔。")
            continue
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
