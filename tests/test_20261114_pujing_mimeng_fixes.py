"""普竞「次数打完」不再误报失败、迷梦推荐阵容轮换、缺游戏窗口的前置判定的回归测试。

三条都来自 2026-11-14 的实跑复盘：
- 普竞连打 5 场全胜后第 6 次点「开始挑战」找不到战斗按钮，旧实现 `return False`
  → 整条任务被记 ✘（次数打完是正常结果）；
- 迷梦每场都用同一套推荐阵容，打不过也不会换；
- 游戏窗口不存在时，任务要白等 2~3 分钟才失败，还会各存一份失败现场，
  把真正需要排查的现场挤掉。

负验证留痕（把对应实现改坏，用例必须变红）：
1. `_finish_without_battle` 的 `return True` 改回 `return False` →
   `test_finish_without_battle_*` 三条变红；
2. `lineup_index_for_round` 去掉取模、直接返回 completed →
   `test_lineup_index_rotates_each_round` 变红；
3. `_preflight_game_window` 直接 `return True` →
   `test_preflight_stops_when_game_window_missing` 变红；
4. `_adopt_ranked_lineup` 里把 `first[1] + index * LINEUP_USE_ROW_STEP` 改回 `first[1]`
   （等于永远点第一行）→ `test_adopt_clicks_use_button_of_target_row` 变红；
5. `handle_battle` 里「上阵人数不满」分支的 `return BATTLE_PARTIAL_TEAM` 改回 `return True`
   （等于拿残缺阵容开打还报成功）→ `test_handle_battle_cancels_partial_team_dialog` 变红。

关于迷梦推荐阵容的界面事实（2026-11-14 实机核对，写在这里免得以后又走回头路）：
入口是「挑战」之后战斗准备界面底部的「阵容推荐」，主界面/玩法目录里没有；
面板里每行右侧绿色「使用」按钮中心相距 180px（370 / 550 / 730），点完当场换阵容并关面板；
推荐列表第一条常是「本轮分享」的半成品（实测只有 2 个上阵），点「战斗」会弹
「上阵人数不满，确认直接开始战斗吗？」，必须点 ✗ 取消后换下一套，点 ✓ 等于白烧一次次数。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot_runtime
import mimengzhiyu
import pujing

tk = pytest.importorskip("tkinter")
import Goldenhandmaidens as gui


def _stub_find(monkeypatch, hits):
    """把 find_center_silent 换成按模板名查表：hits 里出现的模板视为命中。"""
    def fake(template_path, threshold=0.8, **kwargs):
        return (100, 200) if template_path in hits else None
    monkeypatch.setattr(pujing, "find_center_silent", fake)


def _stub_lineup_panel(monkeypatch, close_on_click):
    """桩阵容推荐面板：入口点得到、第一行「使用」在 (1178,370)，第 N 次点后关面板。

    `close_on_click` 大于候选点击次数时模拟「点了也不关」，用来验证降级路径。
    """
    clicks = []
    state = {"gone_calls": 0}

    monkeypatch.setattr(mimengzhiyu, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(
        mimengzhiyu, "find_center_silent",
        lambda path, *a, **k: (1178, 370) if path == mimengzhiyu.tpl_lineup_use
        else (493, 842))
    monkeypatch.setattr(mimengzhiyu, "click_position",
                        lambda pos, *a, **k: clicks.append(pos))
    monkeypatch.setattr(mimengzhiyu, "random_sleep", lambda *a, **k: None)

    def fake_gone(path, timeout, *a, **k):
        state["gone_calls"] += 1
        return state["gone_calls"] >= close_on_click

    monkeypatch.setattr(mimengzhiyu, "_wait_gone", fake_gone)
    return clicks


def test_finish_without_battle_ticket_prompt_is_normal_end(monkeypatch):
    _stub_find(monkeypatch, {pujing.tpl_mianfeimenpiao})
    assert pujing._finish_without_battle() is True


def test_finish_without_battle_keeps_challenge_entry_as_normal_end(monkeypatch):
    # 第 6 次的实际形态：既没有战斗按钮也没有门票图，但挑战入口仍在
    _stub_find(monkeypatch, {pujing.tpl_kaishitiaozhan})
    assert pujing._finish_without_battle() is True


def test_finish_without_battle_unknown_screen_still_fails(monkeypatch):
    _stub_find(monkeypatch, set())
    assert pujing._finish_without_battle() is False


def test_lineup_index_rotates_each_round():
    assert [mimengzhiyu.lineup_index_for_round(i) for i in range(7)] == [0, 1, 2, 0, 1, 2, 0]


def test_lineup_index_fixed_when_rotation_disabled():
    assert mimengzhiyu.lineup_index_for_round(5, rotate=False) == 0


def test_adopt_clicks_use_button_of_target_row(monkeypatch):
    """第 N 套 = 点第 N 行的「使用」（行距 180px），点完面板关闭即成功。"""
    clicks = _stub_lineup_panel(monkeypatch, close_on_click=1)

    assert mimengzhiyu._adopt_ranked_lineup(2) is True
    assert clicks == [(1178, 370 + 2 * mimengzhiyu.LINEUP_USE_ROW_STEP)]


def test_adopt_first_row_needs_no_row_offset(monkeypatch):
    clicks = _stub_lineup_panel(monkeypatch, close_on_click=1)

    assert mimengzhiyu._adopt_ranked_lineup(0) is True
    assert clicks == [(1178, 370)]


def test_adopt_falls_back_to_first_row_when_target_row_missing(monkeypatch):
    """推荐不足 3 套时第 3 行点不关面板：退回第 1 行，而不是卡住或判失败。"""
    clicks = _stub_lineup_panel(monkeypatch, close_on_click=3)

    assert mimengzhiyu._adopt_ranked_lineup(2) is True
    assert clicks[:2] == [(1178, 370 + 2 * mimengzhiyu.LINEUP_USE_ROW_STEP)] * 2
    assert clicks[-1] == (1178, 370)


def test_adopt_gives_up_without_entry(monkeypatch):
    monkeypatch.setattr(mimengzhiyu, "wait_and_click", lambda *a, **k: False)
    assert mimengzhiyu._adopt_ranked_lineup(0) is False


def test_fight_rotation_cancels_partial_lineup_and_tries_next(monkeypatch):
    """第 1 套是半成品（弹「上阵人数不满」）→ 取消后换第 2 套，最终打完一场。"""
    adopted = []
    outcomes = [mimengzhiyu.BATTLE_PARTIAL_TEAM, True]

    monkeypatch.setattr(mimengzhiyu, "_adopt_ranked_lineup",
                        lambda index: adopted.append(index) or True)
    monkeypatch.setattr(mimengzhiyu, "handle_battle", lambda: outcomes.pop(0))

    assert mimengzhiyu._fight_with_lineup_rotation(0, True, True) is True
    assert adopted == [0, 1]


def test_fight_rotation_starts_from_round_index(monkeypatch):
    """第 5 场（completed=4）从第 2 套开始轮换：4 % 3 = 1 → 1, 2, 0。"""
    adopted = []

    monkeypatch.setattr(mimengzhiyu, "_adopt_ranked_lineup",
                        lambda index: adopted.append(index) or True)
    monkeypatch.setattr(mimengzhiyu, "handle_battle",
                        lambda: mimengzhiyu.BATTLE_PARTIAL_TEAM)

    assert mimengzhiyu._fight_with_lineup_rotation(4, True, True) is False
    assert adopted == [1, 2, 0]


def test_fight_rotation_gives_up_when_all_lineups_partial(monkeypatch):
    """三套都残缺时不许拿 2 个英雄去白烧次数。"""
    monkeypatch.setattr(mimengzhiyu, "_adopt_ranked_lineup", lambda index: True)
    monkeypatch.setattr(mimengzhiyu, "handle_battle",
                        lambda: mimengzhiyu.BATTLE_PARTIAL_TEAM)

    assert mimengzhiyu._fight_with_lineup_rotation(0, True, True) is False


def test_fight_rotation_falls_back_to_current_lineup(monkeypatch):
    """采用失败（入口没出现）不该阻断挑战：按当前阵容直接打。"""
    monkeypatch.setattr(mimengzhiyu, "_adopt_ranked_lineup", lambda index: False)
    monkeypatch.setattr(mimengzhiyu, "handle_battle", lambda: True)

    assert mimengzhiyu._fight_with_lineup_rotation(0, True, True) is True


def test_handle_battle_cancels_partial_team_dialog(monkeypatch):
    """「上阵人数不满」确认框 → 点 ✗ 取消（不动 ✓），并上报给上层换阵容。"""
    clicked = []

    def fake_find(template_path, *args, **kwargs):
        if template_path == mimengzhiyu.tpl_tiaoguozhandou:
            return (1000, 800)
        if template_path == mimengzhiyu.tpl_partial_team:
            return (803, 441)
        return None

    monkeypatch.setattr(mimengzhiyu, "find_center_silent", fake_find)
    monkeypatch.setattr(mimengzhiyu, "send_coord", lambda *a, **k: None)
    monkeypatch.setattr(mimengzhiyu, "click_position",
                        lambda pos, *a, **k: clicked.append(pos))
    monkeypatch.setattr(mimengzhiyu, "random_sleep", lambda *a, **k: None)

    assert mimengzhiyu.handle_battle() == mimengzhiyu.BATTLE_PARTIAL_TEAM
    assert clicked == [(803 + mimengzhiyu.PARTIAL_TEAM_CANCEL_OFFSET[0],
                        441 + mimengzhiyu.PARTIAL_TEAM_CANCEL_OFFSET[1])]


@pytest.fixture
def app(tk_root, monkeypatch, tmp_path):
    config_path = tmp_path / "game_bot_config.json"
    monkeypatch.setattr(bot_runtime, "CONFIG_FILE", str(config_path))
    instance = gui.GameBotGUI(tk_root)
    messages = []
    monkeypatch.setattr(instance, "log", messages.append)
    instance.messages = messages
    yield instance
    instance._unregister_hotkeys()
    for child in list(tk_root.winfo_children()):
        child.destroy()


def test_preflight_passes_when_game_window_present(app, monkeypatch):
    monkeypatch.setattr(gui, "is_game_running", lambda: True)
    assert app._preflight_game_window() is True
    assert app.messages == []


def test_preflight_stops_when_game_window_missing(app, monkeypatch):
    monkeypatch.setattr(gui, "is_game_running", lambda: False)
    assert app._preflight_game_window() is False
    assert any("未检测到游戏窗口" in msg for msg in app.messages)
