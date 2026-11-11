"""女神塔登顶回退：登顶后没有下一层，必须先回塔页才能点一键扫荡（不接触真实游戏）。

今日日志证据：挑战到顶后 `nvshentaxiayiceng` 10 秒未出现；随后 `nvshentasaodang`
15 秒未出现、扫荡失败——因为当时停在「再次挑战」页，不是女神塔页面。
"""
import time
import types

import nvshenta as nt

TOWER_PAGE_POS = (3000, 600)


def _stub_back(monkeypatch, saodang_hits, clicks):
    """桩掉回退接缝：扫荡按钮按 saodang_hits 逐次返回，点击只记账不真点。"""
    hits = list(saodang_hits)
    probes = {"count": 0}

    def fake_find(template_path, threshold=0.8, *args, **kwargs):
        if template_path == nt.tpl_nvshentasaodang:
            index = probes["count"]
            probes["count"] += 1
            return TOWER_PAGE_POS if index < len(hits) and hits[index] else None
        return None

    def fake_wait_and_click(template_path, name, threshold=0.8, **kwargs):
        clicks.append((template_path, name, kwargs))
        return True

    monkeypatch.setattr(nt, "find_center_silent", fake_find)
    monkeypatch.setattr(nt, "wait_and_click", fake_wait_and_click)
    # 2026-11-09 起 _back_to_tower_page 在回退两轮后会尝试重进女神塔（退过头到主界面时）；
    # 这里桩成重进失败，保持「只试 exit/exitck」的断言语义。
    monkeypatch.setattr(nt, "open_wanfamulu", lambda *a, **k: False)
    monkeypatch.setattr(nt, "wait_until_loaded", lambda *a, **k: True)
    monkeypatch.setattr(nt, "time", types.SimpleNamespace(time=time.time,
                                                          sleep=lambda _seconds: None))
    return probes


def test_back_to_tower_page_retries_exit_then_finds_saodang(monkeypatch):
    """首查无扫荡按钮 → 点一次 exit → 再查命中，回退成功且只点 exit。"""
    clicks = []
    probes = _stub_back(monkeypatch, [False, True], clicks)

    assert nt._back_to_tower_page() is True
    assert probes["count"] == 2
    assert [name for _tpl, name, _kwargs in clicks] == ["exit"]
    assert clicks[0][2]["timeout"] == 2.0


def test_back_to_tower_page_fails_after_all_attempts(monkeypatch):
    """所有尝试都看不到扫荡按钮时返回 False，并确实试过 exit 与 exitck。"""
    clicks = []
    _stub_back(monkeypatch, [], clicks)

    assert nt._back_to_tower_page(max_attempts=2) is False
    assert [name for _tpl, name, _kwargs in clicks] == ["exit", "exitck", "exit", "exitck"]


def _run_flow(monkeypatch, back_result):
    """驱动 flow_nvshenta 到扫荡段：桩掉挑战循环与所有真实点击。"""
    events = []

    def fake_wait_and_click(template_path, name, *args, **kwargs):
        events.append(name)
        return True

    def fake_back():
        events.append("back")
        return back_result

    def fake_saodang():
        events.append("saodang")
        return True

    monkeypatch.setattr(nt, "wait_and_click", fake_wait_and_click)
    # 进玩法目录已收敛到 common.open_wanfamulu（点后确认目录标题）
    monkeypatch.setattr(nt, "open_wanfamulu", lambda *args, **kwargs: True)
    monkeypatch.setattr(nt, "find_center_silent", lambda *args, **kwargs: None)
    monkeypatch.setattr(nt, "wait_for_battle_start", lambda *args, **kwargs: ("zhandou", (10, 10)))
    monkeypatch.setattr(nt, "wait_for_appearance", lambda *args, **kwargs: None)
    monkeypatch.setattr(nt, "send_coord", lambda *args, **kwargs: None)
    monkeypatch.setattr(nt, "random_sleep", lambda: None)
    monkeypatch.setattr(nt, "_back_to_tower_page", fake_back)
    monkeypatch.setattr(nt, "do_saodang_and_exit", fake_saodang)
    monkeypatch.setattr(nt, "time", types.SimpleNamespace(time=time.time,
                                                          sleep=lambda _seconds: None))
    return events


def test_flow_saodangs_after_back_to_tower_page(monkeypatch):
    """回塔页成功后必须进入扫荡段，且回退发生在扫荡之前。"""
    events = _run_flow(monkeypatch, back_result=True)

    assert nt.flow_nvshenta() is True
    assert events[-2:] == ["back", "saodang"]


def test_flow_does_not_saodang_when_back_fails(monkeypatch):
    """回塔页失败时直接返回 False，不再尝试扫荡。"""
    events = _run_flow(monkeypatch, back_result=False)

    assert nt.flow_nvshenta() is False
    assert "saodang" not in events
