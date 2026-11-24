"""2026-11-24 实跑复盘：女神塔回退后进不去、循环推图空转 11 小时。

1. 女神塔：挑战 1 层后 `_back_to_tower_page` 退回玩法目录，旧实现只看「扫荡」按钮
   （新版界面是一键碾压），且目录已经打开时 `open_wanfamulu` 找不到底栏入口、静默失败，
   于是「重进女神塔」整段被跳过，任务判 ✘。
2. 循环推图：08:41–20:05 连跑 168 轮、没有一次 end(k)——每轮都是阵容练度不足换阵容后
   「阵容用尽」正常结束。原有停止条件（连续失败上限、3 轮快速结束）全都触发不了。
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flow_push
import Goldenhandmaidens as gh
import nvshenta
import push


def test_back_to_tower_page_accepts_crush_page(monkeypatch):
    """页面只剩「一键碾压」时也算回到女神塔页面。"""
    monkeypatch.setattr(nvshenta, "is_loading_screen", lambda: False)
    monkeypatch.setattr(
        nvshenta, "find_center_silent",
        lambda path, *a, **k: (890, 759) if path == nvshenta.tpl_yijiannianya else None,
    )

    assert nvshenta._back_to_tower_page() is True


def test_back_to_tower_page_reenters_when_catalog_open(monkeypatch):
    """已退回玩法目录时：不点底栏入口，直接用目录标题确认并重进女神塔。"""
    clicks = []
    monkeypatch.setattr(nvshenta, "_wait_tower_page", lambda timeout=6.0: False)
    monkeypatch.setattr(
        nvshenta, "find_center_silent",
        lambda path, *a, **k: (900, 100) if path == nvshenta.tpl_catalog_title else None,
    )
    monkeypatch.setattr(nvshenta, "wait_and_click",
                        lambda path, name, *a, **k: clicks.append(name) or True)
    monkeypatch.setattr(nvshenta, "wait_until_loaded", lambda *a, **k: True)
    monkeypatch.setattr(nvshenta, "open_wanfamulu", lambda *a, **k: False)
    monkeypatch.setattr(nvshenta, "_reenter_tower", lambda: True)
    monkeypatch.setattr(nvshenta, "time", type("T", (), {"sleep": lambda self, s: None})())

    assert nvshenta._back_to_tower_page() is True
    # 目录页上不再点 exit（会把界面退到更外层），直接重进
    assert clicks == []


def test_flow_push_records_stage_cleared(monkeypatch):
    """flow_push_mode1 必须把「本轮是否推过关」透出给循环推图。"""

    class FakeFlow:
        def __init__(self, *args, **kwargs):
            self.stop_reason = "lineup_exhausted"
            self.stage_cleared = True

        def run(self):
            return True

    monkeypatch.setattr(push, "init_templates_from_dir", lambda: None)
    monkeypatch.setattr(push, "PushFlow", FakeFlow)

    assert push.flow_push_mode1() is True
    assert push.LAST_STOP_REASON == "lineup_exhausted"
    assert push.LAST_STAGE_CLEARED is True


def _fake_gui(logs):
    gui = object.__new__(gh.GameBotGUI)
    gui.stop_event = threading.Event()
    gui.config = {"push_settings": {}}
    gui.log = lambda msg, *a, **k: logs.append(msg)
    gui._ensure_loop_ready = lambda: True
    return gui


class _FakeClock:
    """可控时钟：每调用一次推图推进 60 秒，避免命中原有的「3 轮快速结束」规则。"""

    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(float(seconds), 0.01)


def test_loop_stops_after_two_no_progress_rounds(monkeypatch):
    """两种推图都正常结束但一步没推进：第 2 轮后必须停，而不是无限循环。"""
    logs = []
    gui = _fake_gui(logs)
    clock = _FakeClock()

    def fake_main(**kwargs):
        clock.now += 60
        return True

    monkeypatch.setattr(gh, "time", clock)
    monkeypatch.setattr(flow_push, "main", fake_main)
    monkeypatch.setattr(push, "main", fake_main)
    monkeypatch.setattr(flow_push, "LAST_STOP_REASON", "")
    monkeypatch.setattr(push, "LAST_STOP_REASON", "lineup_exhausted")
    monkeypatch.setattr(push, "LAST_STAGE_CLEARED", False)

    assert gui._run_xunhuan(None) is True
    assert any("第 2 轮 - 幻灵推图开始" in m for m in logs)
    assert not any("第 3 轮 - 幻灵推图开始" in m for m in logs)
    assert any("没有任何推进" in m for m in logs)


def test_loop_continues_while_rounds_clear_stages(monkeypatch):
    """有推进就继续循环，不会在第 2 轮被「无进展」规则误停。"""
    logs = []
    gui = _fake_gui(logs)
    clock = _FakeClock()

    def fake_main(**kwargs):
        clock.now += 60
        return True

    def log_and_maybe_stop(msg, *a, **k):
        logs.append(msg)
        if "第 3 轮完成" in msg:
            gui.stop_event.set()

    gui.log = log_and_maybe_stop
    monkeypatch.setattr(gh, "time", clock)
    monkeypatch.setattr(flow_push, "main", fake_main)
    monkeypatch.setattr(push, "main", fake_main)
    monkeypatch.setattr(flow_push, "LAST_STOP_REASON", "")
    monkeypatch.setattr(push, "LAST_STOP_REASON", "")
    monkeypatch.setattr(push, "LAST_STAGE_CLEARED", True)

    assert gui._run_xunhuan(None) is True
    assert any("第 3 轮完成" in m for m in logs)
    assert not any("没有任何推进" in m for m in logs)
