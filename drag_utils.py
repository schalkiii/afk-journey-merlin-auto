"""拖拽 / 长按工具模块：把「按住左键拖」和「原地长按」收敛成一处。

关键接口：
- send_drag(x1, y1, x2, y2, hold_ms=None): 按住左键从起点拖到终点；给了 hold_ms
  就变成「在起点按住 hold_ms 毫秒再松开」（迷宫长按场景）。

实现走 `common.inject_drag` 的进程内 SendInput（2026-11-17 起）：按下与抬起都在本
进程内提交，不再经过「写 txt 等外部注入器消费」的中间层，因此也没有需要等待的外部
消费者（旧的 `wait_for_drag_complete` 已随之删除）。
"""

import common

# ============================================================
# 通用拖拽函数
# ============================================================

def send_drag(x1: int, y1: int, x2: int, y2: int, hold_ms: int | None = None):
    """按住左键拖动 / 长按，返回是否注入成功。

    hold_ms 不为 None 时只在起点长按（忽略 x2/y2），用于「长按 4 秒」这类操作。
    短按拖动逐步移动才能触发 Unity 的 ScrollRect（见 common.inject_drag）。
    """
    # 非前台时第一次按下会被系统吞掉去激活窗口，与点击同理：先确保游戏可点。
    if common.ensure_game_clickable() is False:
        common._click_title_bar()
    return common.inject_drag(x1, y1, x2, y2, hold_ms=hold_ms)
