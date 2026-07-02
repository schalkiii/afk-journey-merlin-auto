import os
import time
from common import get_work_path

# ============================================================
# 常量
# ============================================================

DRAG_COORD_PATH = get_work_path("shared\\drag_coord.txt")

# 确保 shared 目录存在
os.makedirs(os.path.dirname(DRAG_COORD_PATH), exist_ok=True)

# ============================================================
# 通用拖拽函数
# ============================================================

def send_drag(x1: int, y1: int, x2: int, y2: int, hold_ms: int = None):
    """
    将一次拖拽指令写入文件，交给 AHK 脚本执行。
    AHK 从 (x1, y1) 按下左键，拖到 (x2, y2) 后松开。
    hold_ms: 可选，按住时长(ms)，不传则使用 AHK 默认值
    """
    with open(DRAG_COORD_PATH, "w", encoding="utf-8") as f:
        if hold_ms is not None:
            f.write(f"{x1} {y1} {x2} {y2} {hold_ms}")
        else:
            f.write(f"{x1} {y1} {x2} {y2}")


def wait_for_drag_complete(check_interval: float = 0.05, timeout: float = 10.0) -> bool:
    """
    等待 AHK 处理完拖拽指令（文件被删除即为处理完毕）。
    """
    elapsed = 0.0
    while os.path.exists(DRAG_COORD_PATH):
        time.sleep(check_interval)
        elapsed += check_interval
        if elapsed > timeout:
            print("⚠️ 等待拖拽完成超时，请检查 AHK 是否在运行")
            return False
    return True