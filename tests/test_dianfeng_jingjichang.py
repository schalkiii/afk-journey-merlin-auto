"""巅峰竞技场流程的单元测试（不接触真实游戏）。"""
import dianfengjingjichang as df


def test_fight_once_full_selection_flow(monkeypatch):
    """继续挑战 → 选对手 → 连点两次「编辑下一场」→ 战斗 → 失败结算 → 回到挑战界面。"""
    state = {"bianji": 0}
    clicks = []

    def fake_find(template_path, threshold=0.8, timeout=0, **kwargs):
        if template_path == df.tpl_xuanzeduishou:
            return (700, 120)
        if template_path == df.tpl_tiaozhan:
            return (800, 840)
        if template_path == df.tpl_bianji:
            state["bianji"] += 1
            return (800, 840) if state["bianji"] <= 2 else None
        if template_path == df.tpl_zhandou:
            return (800, 840) if state["bianji"] >= 2 else None
        if template_path == df.tpl_fail:
            return (800, 300)
        if template_path == df.tpl_jixutiaozhan:
            return (800, 840)
        return None

    def fake_click(pos, wait=1.5, twice=True):
        clicks.append(pos)
        return True

    monkeypatch.setattr(df, "find_center_silent", fake_find)
    monkeypatch.setattr(df, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(df, "click_position", fake_click)
    monkeypatch.setattr(df, "game_client_region", lambda *a, **k: (100, 50, 1600, 900))
    monkeypatch.setattr(df, "random_sleep", lambda: None)
    monkeypatch.setattr(df, "dismiss_popup_away_from", lambda: None)
    monkeypatch.setattr(df.time, "sleep", lambda _s: None)

    assert df._fight_once(1) is True
    # 只有对手卡片用固定点位点击；其它按钮都走 wait_and_click
    assert clicks == [(772, 472)]


def test_fight_once_stops_when_no_continue_button(monkeypatch):
    """没有「继续挑战」时立即结束，不会盲点战斗/跳过。"""
    monkeypatch.setattr(df, "wait_and_click", lambda *a, **k: False)
    assert df._fight_once(1) is False


def test_fight_once_stops_when_opponent_screen_missing(monkeypatch):
    """点完继续挑战却没进入选择对手：不进入阵容/战斗步骤。"""
    monkeypatch.setattr(df, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(df, "find_center_silent", lambda *a, **k: None)
    monkeypatch.setattr(df, "game_client_region", lambda *a, **k: (0, 0, 1600, 900))
    monkeypatch.setattr(df, "random_sleep", lambda: None)

    assert df._fight_once(1) is False
