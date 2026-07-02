from common import find_center, send_coord, get_template_path
import time

def check_and_handle_libao(timeout=5.0, interval=0.5):
    """
    检测并处理礼包弹窗
    
    参数:
        timeout: 连续检测不到礼包的秒数，超过此时间则退出
        interval: 检测间隔（秒）
    
    返回:
        True: 检测到并处理了礼包
        False: 未检测到礼包
    """
    libao_template = get_template_path("libao.png")
    tuichulibao_template = get_template_path("tuichulibao.png")
    last_detected_time = None
    start_time = time.time()
    
    while True:
        pos = find_center(libao_template, threshold=0.8)
        
        if pos:
            print(f"检测到礼包，位置: {pos}")
            
            last_detected_time = time.time()
            
            close_pos = find_center(tuichulibao_template, threshold=0.8)
            
            if close_pos:
                print(f"检测到退出礼包按钮，位置: {close_pos}")
                print(f"点击退出礼包按钮: {close_pos}")
                send_coord(close_pos[0], close_pos[1])
            else:
                print("未检测到退出礼包按钮")
            
            time.sleep(interval)
        else:
            if last_detected_time is not None:
                elapsed = time.time() - last_detected_time
                if elapsed >= timeout:
                    print(f"连续 {timeout} 秒未检测到礼包，检测结束")
                    return True
            else:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    print(f"{timeout} 秒内未检测到礼包，检测结束")
                    return False
        
        time.sleep(interval)

if __name__ == "__main__":
    print("开始检测礼包...")
    check_and_handle_libao()
    print("检测脚本结束")
