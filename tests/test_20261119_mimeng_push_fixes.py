"""2026-11-19 实跑复盘的两条修复。

1. 迷梦之域：点「使用」推荐阵容后会弹「采用对方阵容会盖当前队伍中的英雄、旧日回响和
   站位，是否确认采用？」确认框；旧实现以为面板已关，回到准备界面时战斗按钮被盖住，
   handle_battle 直接判失败。当天已经打完 1 场、次数也用了，整项却记 ✘。
   顺带把「推荐阵容全部不可用 / 已有战果后无法继续」收成正常结束，避免「用了次数报失败」。
2. 推图：advance 点击被窗口激活吞掉时没有确认切页，流程在玩法目录上找入口白等 10 秒；
   另外赛季普通关卡清完后页面只剩「幻灵挑战」入口，旧实现判失败，应正常结束。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mimengzhiyu
import push


def test_confirm_adopt_dialog_clicks_ok_offset(monkeypatch):
    """确认框标题命中后，点它右下方固定偏移的「确定」，消失即处理成功。"""
    clicked = []
    state = {"shown": True}

    def fake_find(path, *args, **kwargs):
        if path == mimengzhiyu.tpl_adopt_confirm and state["shown"]:
            return (840, 355)
        return None

    def fake_click(pos, *args, **kwargs):
        clicked.append(pos)
        state["shown"] = False

    monkeypatch.setattr(mimengzhiyu, "find_center_silent", fake_find)
    monkeypatch.setattr(mimengzhiyu, "click_position", fake_click)

    assert mimengzhiyu._confirm_adopt_dialog() is True
    assert clicked == [(840 + mimengzhiyu.ADOPT_CONFIRM_OK_OFFSET[0],
                        355 + mimengzhiyu.ADOPT_CONFIRM_OK_OFFSET[1])]


def test_confirm_adopt_dialog_absent_does_nothing(monkeypatch):
    clicked = []
    monkeypatch.setattr(mimengzhiyu, "find_center_silent", lambda *a, **k: None)
    monkeypatch.setattr(mimengzhiyu, "click_position",
                        lambda pos, *a, **k: clicked.append(pos))

    assert mimengzhiyu._confirm_adopt_dialog() is False
    assert clicked == []


def test_adopt_ranked_lineup_calls_confirm_after_use(monkeypatch):
    """点「使用」之后必须处理采用确认框，否则准备界面被盖住。"""
    confirmed = []
    monkeypatch.setattr(mimengzhiyu, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(
        mimengzhiyu, "find_center_silent",
        lambda path, *a, **k: (1178, 370) if path == mimengzhiyu.tpl_lineup_use else None,
    )
    monkeypatch.setattr(mimengzhiyu, "click_position", lambda *a, **k: None)
    monkeypatch.setattr(mimengzhiyu, "random_sleep", lambda *a, **k: None)
    monkeypatch.setattr(mimengzhiyu, "_wait_gone", lambda *a, **k: True)
    monkeypatch.setattr(mimengzhiyu, "_confirm_adopt_dialog",
                        lambda: confirmed.append(1) or True)

    assert mimengzhiyu._adopt_ranked_lineup(0) is True
    assert confirmed == [1]


def _stub_finish(monkeypatch):
    """把收尾动作换成记录桩，避免用例里真的去点界面。"""
    calls = []
    monkeypatch.setattr(mimengzhiyu, "close_result_popups",
                        lambda *a, **k: calls.append("close") or True)
    monkeypatch.setattr(mimengzhiyu, "_exit_to_main",
                        lambda *a, **k: calls.append("exit") or True)
    return calls


def test_finish_without_fight_lineup_exhausted_is_normal_end(monkeypatch):
    calls = _stub_finish(monkeypatch)
    mimengzhiyu.LAST_STOP_REASON = ""

    assert mimengzhiyu._finish_without_fight(
        mimengzhiyu.BATTLE_LINEUP_EXHAUSTED, 0) is True
    assert mimengzhiyu.LAST_STOP_REASON == "lineup_exhausted"
    assert calls == ["close", "exit"]


def test_finish_without_fight_after_completed_is_normal_end(monkeypatch):
    """已经打完至少一场（次数已用），后续打不了也按完成收尾。"""
    calls = _stub_finish(monkeypatch)
    mimengzhiyu.LAST_STOP_REASON = ""

    assert mimengzhiyu._finish_without_fight(False, 1) is True
    assert mimengzhiyu.LAST_STOP_REASON == "completed"
    assert calls == ["close", "exit"]


def test_finish_without_fight_before_any_completion_is_failure(monkeypatch):
    calls = _stub_finish(monkeypatch)
    mimengzhiyu.LAST_STOP_REASON = ""

    assert mimengzhiyu._finish_without_fight(False, 0) is False
    assert mimengzhiyu.LAST_STOP_REASON == ""
    assert calls == []


def test_normal_entry_cleared_when_only_huanling_visible(monkeypatch):
    def fake_find(path, *args, **kwargs):
        return (900, 750) if path == push.tpl_huanlingcha else None

    monkeypatch.setattr(push, "find_center_silent", fake_find)

    assert push._normal_entry_cleared() is True


def test_normal_entry_cleared_false_when_challenge_visible(monkeypatch):
    def fake_find(path, *args, **kwargs):
        if path in (push.tpl_tiaozhan, push.tpl_tiaozhanonly, push.tpl_huanlingcha):
            return (900, 750)
        return None

    monkeypatch.setattr(push, "find_center_silent", fake_find)

    assert push._normal_entry_cleared() is False


def _stub_enter(monkeypatch, flow, states):
    """把 _st_enter 的外部动作都换成桩；states 依次作为页面锚点探测结果。"""
    names = []
    monkeypatch.setattr(push, "open_wanfamulu", lambda **kwargs: True)
    monkeypatch.setattr(flow, "_wait_after_action", lambda *a, **k: push.tpl_advance)
    monkeypatch.setattr(push, "wait_and_click",
                        lambda path, name, *a, **k: names.append(name) or True)
    monkeypatch.setattr(flow, "_wait_for_any_state",
                        lambda *a, **k: states.pop(0) if states else None)
    return names


def test_st_enter_ends_normally_when_season_cleared(monkeypatch):
    """普通关卡清完、只剩幻灵挑战：返回 done(True) 并记录 season_cleared。"""
    flow = push.PushFlow(mode="normal", claim_first_clear=False)
    _stub_enter(monkeypatch, flow, [push.tpl_huanlingcha])
    monkeypatch.setattr(flow, "_enter_mode_and_confirm", lambda: None)
    monkeypatch.setattr(push, "_normal_entry_cleared", lambda: True)

    assert flow._st_enter() == push.STATE_DONE
    assert flow.finished_ok is True
    assert flow.stop_reason == "season_cleared"


def test_st_enter_retries_advance_when_page_does_not_change(monkeypatch):
    """advance 点击被吞（页面仍是玩法目录）时补点一次，而不是直接进领取/等入口。"""
    flow = push.PushFlow(mode="normal", claim_first_clear=False)
    names = _stub_enter(monkeypatch, flow, [None, push.tpl_tiaozhan])
    monkeypatch.setattr(flow, "_enter_mode_and_confirm", lambda: push.tpl_autocha)

    assert flow._st_enter() == push.STATE_START_BATTLE
    assert names == ["advance(a)", "advance(a_retry)"]
