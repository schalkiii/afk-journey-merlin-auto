"""2026-11-28 实机修复：巅峰竞技场点「挑战他」被吞后补点。

今天 08:11:26 点完「挑战他」，6 秒内既没等到「战斗」也没等到「编辑下一场」，
直接判「完成 0 场」，整项 44.5 秒失败。此时按钮若仍在屏上，说明那一下点击被吞
（首次点击常被窗口激活吃掉），补点一次即可继续。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dianfengjingjichang as df


def _stub_select(monkeypatch, *, swallowed, retry_enters_lineup):
    """选对手 → 挑战他。

    `swallowed=True`：第一次点击被吞，「挑战他」仍在屏上；
    `retry_enters_lineup=True`：补点后阵容页出现（「战斗」可见）。
    """
    names = []
    state = {"challenge": True, "lineup": False}
    monkeypatch.setattr(df, "game_client_region", lambda: (0, 0, 1600, 900))
    monkeypatch.setattr(df, "click_position", lambda pos, **kwargs: None)
    monkeypatch.setattr(df, "dismiss_popup_away_from", lambda: False)
    monkeypatch.setattr(df.time, "sleep", lambda _seconds: None)

    def fake_find(template_path, threshold=0.8, timeout=0.0, **kwargs):
        if template_path == df.tpl_xuanzeduishou:
            return (900, 400)
        if template_path == df.tpl_tiaozhan:
            if state["lineup"]:
                return None
            return (1200, 970) if state["challenge"] else None
        return None

    def fake_wait_click(template_path, name, *args, **kwargs):
        names.append(name)
        if "补点" in str(name):
            if retry_enters_lineup:
                state["lineup"] = True
        elif not swallowed:
            state["challenge"] = False   # 点击生效，页面已经切换
        return True

    wait_calls = {"n": 0}

    def fake_wait_any(templates, timeout, interval=0.5, quiet=False):
        wait_calls["n"] += 1
        if wait_calls["n"] == 1:
            return None                       # 第一次：阵容页没出现
        return (df.tpl_zhandou, (1200, 970))

    monkeypatch.setattr(df, "find_center_silent", fake_find)
    monkeypatch.setattr(df, "wait_and_click", fake_wait_click)
    monkeypatch.setattr(df, "_wait_for_any", fake_wait_any)
    return names


def test_lineup_page_retry_after_swallowed_challenge_click(monkeypatch):
    names = _stub_select(monkeypatch, swallowed=True, retry_enters_lineup=True)

    assert df._select_opponent_and_lineup() is True
    assert any("补点" in str(name) for name in names)


def test_lineup_page_gives_up_when_challenge_button_gone(monkeypatch):
    """「挑战他」已经不在了（页面确实变了）且没等到阵容页：不盲点，按失败结束。"""
    names = _stub_select(monkeypatch, swallowed=False, retry_enters_lineup=False)

    assert df._select_opponent_and_lineup() is False
    assert not any("补点" in str(name) for name in names)
