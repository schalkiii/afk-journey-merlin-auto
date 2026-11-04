"""红点领取模块：领取循环的计数、停止条件与上限保护。"""
import types

import numpy as np

import hongbaolingqu as hb


def test_claim_stops_when_nothing_left(monkeypatch):
    monkeypatch.setattr(hb, "wait_and_click", lambda *args, **kwargs: False)
    monkeypatch.setattr(hb, "find_center_silent", lambda *args, **kwargs: None)
    assert hb.claim_current_view() == 0


def test_claim_loop_uses_both_buttons_and_closes_popup(monkeypatch):
    """一键领取与单个领取混着出现时都要点到，且每次领取后都尝试关奖励弹窗。"""
    actions = []
    # 第 1 轮有一键领取，第 2 轮只剩单个领取，第 3 轮两者都没有
    yijian_results = iter([True, False, False])
    lingqu_results = iter([(1100, 400), None])

    def fake_wait_and_click(template_path, name, *args, **kwargs):
        if template_path == hb.tpl_yijianlingqu:
            return next(yijian_results)
        return False

    def fake_find(template_path, *args, **kwargs):
        if template_path == hb.tpl_blank_close:
            actions.append("close")
            return (100, 100)
        if template_path == hb.tpl_lingqu:
            return next(lingqu_results)
        return None

    monkeypatch.setattr(hb, "wait_and_click", fake_wait_and_click)
    monkeypatch.setattr(hb, "find_center_silent", fake_find)
    monkeypatch.setattr(hb, "click_blank_to_exit", lambda *args, **kwargs: actions.append("blank"))
    monkeypatch.setattr(hb, "click_position", lambda pos, **kwargs: actions.append(("click", pos)))

    assert hb.claim_current_view() == 2
    assert actions == [
        "close", "blank",
        ("click", (1100, 400)), "close", "blank",
    ]


def test_claim_loop_stops_at_cap(monkeypatch):
    """领取后界面不刷新时靠上限退出，不能死循环点同一个按钮。"""
    monkeypatch.setattr(hb, "wait_and_click", lambda *args, **kwargs: True)
    monkeypatch.setattr(hb, "find_center_silent", lambda *args, **kwargs: None)
    monkeypatch.setattr(hb, "click_blank_to_exit", lambda *args, **kwargs: None)
    assert hb.claim_current_view() == hb.MAX_CLAIM_PER_VIEW


def test_task_panel_falls_back_to_hud_target_entry(monkeypatch):
    """菜单→任务 进不去时改用主界面左下角「目标」直达入口，而不是直接放弃整个面板。"""
    tried = []
    monkeypatch.setattr(hb, "_open_task_panel_via_menu", lambda: False)
    monkeypatch.setattr(hb, "log", lambda *args, **kwargs: None)

    def fake_hud_entry():
        tried.append("hud")
        return True

    monkeypatch.setattr(hb, "_open_task_panel_via_hud", fake_hud_entry)

    assert hb._open_task_panel() is True
    assert tried == ["hud"]


def test_hud_target_entry_adds_client_origin(monkeypatch):
    """HUD 固定点位必须换算成整屏坐标——历史上多次因为直接把客户区坐标传进去而点空。"""
    clicks = []
    monkeypatch.setattr(hb, "check_stop", lambda: None)
    monkeypatch.setattr(hb, "game_client_region", lambda: (2000, 100, 1600, 900))
    monkeypatch.setattr(hb, "click_position", lambda pos, **kwargs: clicks.append(pos))
    monkeypatch.setattr(hb, "_panel_open", lambda: True)
    monkeypatch.setattr(hb, "time", types.SimpleNamespace(sleep=lambda *args: None))
    monkeypatch.setattr(hb, "log", lambda *args, **kwargs: None)

    assert hb._open_task_panel_via_hud() is True
    assert clicks[0] == (2000 + hb.TASK_PANEL_HUD_POS[0], 100 + hb.TASK_PANEL_HUD_POS[1])
    assert clicks[0] != hb.TASK_PANEL_HUD_POS


def _stub_journal(monkeypatch, switch_changed):
    """桩掉一记扫描的外部依赖；switch_changed 表示「子页签行是否确认发生了切换」。"""
    clicks = []
    swept = []
    monkeypatch.setattr(hb, "check_stop", lambda: None)
    monkeypatch.setattr(hb, "log", lambda *args, **kwargs: None)
    monkeypatch.setattr(hb, "game_client_region", lambda: (2000, 100, 1600, 900))
    monkeypatch.setattr(hb, "click_position", lambda pos, **kwargs: clicks.append(pos))
    monkeypatch.setattr(hb, "get_cached_screenshot",
                        lambda: np.zeros((900, 1600, 3), dtype=np.uint8))
    # 子页签行真切了会掉到 -0.3（实测），没切是 1.000；这里直接桩掉分数
    monkeypatch.setattr(hb.cv2, "matchTemplate",
                        lambda *args, **kwargs: np.array([[-0.3] if switch_changed else [1.0]]))

    def fake_sweep(view_name):
        swept.append(view_name)
        return 1

    monkeypatch.setattr(hb, "_sweep_view", fake_sweep)
    return clicks, swept


def test_journal_sweeps_three_task_sub_tabs_when_switch_confirmed(monkeypatch):
    """切页确认成功时，每日/每周/挑战三个子页签都要扫——漏掉就是整片周常奖励不领。"""
    clicks, swept = _stub_journal(monkeypatch, switch_changed=True)

    assert hb._sweep_journal("测试记") == 4
    assert sorted(s for s in swept if "任务子页" in s) == [
        "测试记-任务子页1", "测试记-任务子页2", "测试记-任务子页3"]
    # 扫完切回奖励页，让下一本记从已知状态开始
    assert clicks[-1] == (2000 + hb.JOURNAL_REWARD_TAB_POS[0], 100 + hb.JOURNAL_REWARD_TAB_POS[1])


def test_journal_stops_when_sub_tab_row_did_not_move(monkeypatch):
    """子页签行没动就说明没在任务页上，必须停：那三个坐标在奖励页落在奖励列表区。"""
    clicks, swept = _stub_journal(monkeypatch, switch_changed=False)

    assert hb._sweep_journal("测试记") == 1
    assert swept == ["测试记-奖励"]
    assert len(clicks) == 3, "只应点 切任务页 + 两个子页签试探，不能继续扫下去"
