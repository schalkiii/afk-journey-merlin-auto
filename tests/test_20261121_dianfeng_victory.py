"""2026-11-21 实跑复盘：巅峰竞技场认不出「战斗胜利」结算页。

今天跳过之后出现的是「战斗胜利 3:0」结果页（同屏 `jieshengli` 0.981、
底部 `pujingjieshu` 0.971），旧实现只等 `fail / 继续挑战`，20 秒后按
「始终无法识别界面」放弃，把一场已经打赢、次数已经消耗的比赛记成「完成 0 场」并判 ✘。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dianfengjingjichang as df


def _fake_find_factory(state):
    def fake_find(template_path, threshold=0.8, timeout=0, **kwargs):
        if template_path == df.tpl_xuanzeduishou:
            return (700, 120)
        if template_path == df.tpl_tiaozhan:
            return (800, 840)
        if template_path == df.tpl_bianji:
            state["lineup"] += 1
            return (800, 840) if state["lineup"] <= 2 else None
        if template_path == df.tpl_zhandou:
            return (800, 840) if state["lineup"] >= 2 and not state["dismissed"] else None
        if not state["dismissed"]:
            if template_path == df.tpl_shengli and state["show_shengli"]:
                return (800, 180)
            if template_path == df.tpl_jiesuan:
                return (800, 830)
        if template_path == df.tpl_jixutiaozhan and state["dismissed"]:
            return (800, 840)
        return None

    return fake_find


def _run_fight(monkeypatch, show_shengli):
    state = {"lineup": 0, "dismissed": False, "show_shengli": show_shengli}
    clicks = []
    settlement_points = {
        (100 + df.SETTLEMENT_DISMISS_POS[0], 50 + df.SETTLEMENT_DISMISS_POS[1]),
        (800, 830),   # 结算页底部「点击空白处关闭」
    }

    def fake_click(pos, wait=1.5, twice=True):
        clicks.append(pos)
        if pos in settlement_points:
            state["dismissed"] = True
        return True

    monkeypatch.setattr(df, "find_center_silent", _fake_find_factory(state))
    monkeypatch.setattr(df, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(df, "click_position", fake_click)
    monkeypatch.setattr(df, "game_client_region", lambda *a, **k: (100, 50, 1600, 900))
    monkeypatch.setattr(df, "random_sleep", lambda: None)
    monkeypatch.setattr(df, "dismiss_popup_away_from", lambda: None)
    monkeypatch.setattr(df, "log", lambda *a, **k: None)
    monkeypatch.setattr(df.time, "sleep", lambda _s: None)
    return df._fight_once(1), clicks, state


def test_outcome_signals_include_victory_page(monkeypatch):
    """两个等待阶段都必须把胜利页与结算页底部提示当信号。"""
    captured = []

    def fake_poll(signals, **kwargs):
        captured.append([tpl for tpl, _name in signals])

    monkeypatch.setattr(df, "_poll_until_outcome", fake_poll)

    df._settle_after_skip((800, 700))
    df._wait_for_battle_outcome()

    assert len(captured) == 2
    for signals in captured:
        assert df.tpl_shengli in signals
        assert df.tpl_jiesuan in signals


def test_fight_once_counts_victory_page_and_closes_it(monkeypatch):
    """胜利页要算完成一场，并用面板外的空白点关掉结算。"""
    ok, clicks, _state = _run_fight(monkeypatch, show_shengli=True)

    assert ok is True
    assert clicks[-1] == (
        100 + df.SETTLEMENT_DISMISS_POS[0], 50 + df.SETTLEMENT_DISMISS_POS[1])


def test_fight_once_clicks_settlement_footer_when_matched(monkeypatch):
    """命中结算页底部「点击空白处关闭」时直接点它，而不是固定空白点。"""
    ok, clicks, _state = _run_fight(monkeypatch, show_shengli=False)

    assert ok is True
    assert clicks[-1] == (800, 830)
