"""2026-11-23 实跑复盘：许愿活动页挡住回主界面、女神塔新版「一键碾压」、双实例互踩。

今天早上三个实例前后脚在跑（08:01:03 定时、08:01:06 第二次启动、08:23 第三次），
点击互相打断，女神塔 / 英雄厅堂 / 爬塔 / 红点领取连环失败；红点领取前又被家园「许愿」
活动页挡住（页面只有「退出」按钮，没有 exit/exitck 模板），连续 3 项被跳过触发熔断，
收尾逻辑随后关闭了游戏——用户看到的就是「运行到领红点游戏退出了」。
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common
import Goldenhandmaidens as gh
import nvshenta


def test_recover_clicks_wish_exit_button(monkeypatch):
    """「许愿」活动页只认「退出」按钮：点完必须能继续走到主界面。"""
    state = {"clicked": False}
    tpl_wish = common.get_template_path("xuyuantuichu.png")

    def fake_find(template_path, *args, **kwargs):
        if template_path == tpl_wish and not state["clicked"]:
            return (787, 675)
        return None

    def fake_send(x, y):
        # 只有点在「退出」按钮上才算关掉；空白兜底点不算（否则负验证会假绿）
        if (x, y) == (787, 675):
            state["clicked"] = True

    monkeypatch.setattr(common, "find_center_silent", fake_find)
    monkeypatch.setattr(common, "send_coord", fake_send)
    monkeypatch.setattr(common, "at_main_interface", lambda *a, **k: state["clicked"])
    monkeypatch.setattr(common, "check_stop", lambda: None)
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)

    assert common.recover_to_main_interface() is True
    assert state["clicked"] is True


def test_tower_page_open_accepts_crush_button(monkeypatch):
    """新版女神塔页面（层卡片 + 一键碾压）必须算作「已进入」。"""
    monkeypatch.setattr(nvshenta, "is_loading_screen", lambda: False)
    monkeypatch.setattr(
        nvshenta, "find_center_silent",
        lambda path, *a, **k: (890, 759) if path == nvshenta.tpl_yijiannianya else None,
    )

    assert nvshenta._tower_page_open() is True


def test_crush_and_exit_clicks_then_leaves(monkeypatch):
    """一键碾压：点一次、等按钮消失、退出并检测礼包。"""
    actions = []
    visible = {"n": 1}

    def fake_visible(threshold=0.8):
        visible["n"] -= 1
        return (890, 759) if visible["n"] >= 0 else None

    monkeypatch.setattr(nvshenta, "_yijiannianya_visible", fake_visible)
    monkeypatch.setattr(nvshenta, "send_coord", lambda x, y: actions.append(("click", x, y)))
    monkeypatch.setattr(nvshenta, "find_center_silent", lambda *a, **k: None)
    monkeypatch.setattr(nvshenta, "wait_and_click",
                        lambda path, name, *a, **k: actions.append(("wc", name)) or True)
    monkeypatch.setattr(nvshenta, "random_sleep", lambda *a, **k: None)
    monkeypatch.setattr(nvshenta, "check_and_handle_libao", lambda *a, **k: None)
    monkeypatch.setattr(nvshenta.time, "sleep", lambda _s: None)

    assert nvshenta._crush_and_exit((890, 759)) is True
    assert actions[0] == ("click", 890, 759)
    assert ("wc", "exitck(女神塔)") in actions


def test_second_instance_is_rejected():
    """已有同名互斥体时，第二个实例必须被拒绝。"""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, gh.INSTANCE_MUTEX_NAME)
    try:
        assert gh._acquire_instance_mutex() is False
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
