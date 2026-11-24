"""2026-11-24 性能：仓库练度全为「巅峰+」时跳过逐套阵容识别。

实测每套阵容要识别 5 个头像（168 张模板 × 9 个尺度 × 2 套布局 ≈ 1.5 万次匹配），
耗时 5~6 秒；而快照全「高」时练度判定恒真，这部分识别纯属浪费。
只要出现一个「低 / 未拥有」，快速路径自动失效，回到完整判定。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import push


def test_all_levels_high_only_when_every_level_is_high():
    assert push._all_levels_high({"ade": "高", "meimo": "高"}) is True
    assert push._all_levels_high({"ade": "高", "meimo": "低"}) is False
    assert push._all_levels_high({"ade": "高", "meimo": "未拥有"}) is False
    assert push._all_levels_high({}) is False


def _stub_select(monkeypatch, levels):
    """驱动一次 _st_lineup_select：记录识别调用，采用成功即返回。"""
    flow = push.PushFlow(mode="normal", skip_manual=False, claim_first_clear=False)
    calls = {"recognize": 0, "oneclick": 0}
    monkeypatch.setattr(push, "find_center_silent", lambda *a, **k: None)
    monkeypatch.setattr(push, "_load_warehouse_levels", lambda: levels)

    def fake_recognize():
        calls["recognize"] += 1
        return [], None

    def fake_click(path, name, *a, **k):
        if path == push.tpl_oneclick:
            calls["oneclick"] += 1
        return True

    monkeypatch.setattr(push, "_recognize_lineup_with_levels", fake_recognize)
    monkeypatch.setattr(push, "_is_lineup_acceptable", lambda *a, **k: True)
    monkeypatch.setattr(push, "wait_and_click", fake_click)
    monkeypatch.setattr(flow, "_wait_for_any_state", lambda *a, **k: push.tpl_autocha)
    return flow, calls


def test_lineup_select_skips_recognition_when_all_high(monkeypatch):
    """全「高」：不调用头像识别，直接采用第一套。"""
    flow, calls = _stub_select(monkeypatch, {"ade": "高", "meimo": "高"})

    assert flow._st_lineup_select() == push.STATE_START_BATTLE
    assert calls == {"recognize": 0, "oneclick": 1}


def test_lineup_select_uses_recognition_when_any_low(monkeypatch):
    """出现「低」时必须回到完整识别，不能走快速路径。"""
    flow, calls = _stub_select(monkeypatch, {"ade": "高", "meimo": "低"})

    assert flow._st_lineup_select() == push.STATE_START_BATTLE
    assert calls == {"recognize": 1, "oneclick": 1}
