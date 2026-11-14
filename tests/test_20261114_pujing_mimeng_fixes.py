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
   `test_preflight_stops_when_game_window_missing` 变红。
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


def test_adopt_ranked_lineup_clicks_next_arrow_index_times(monkeypatch):
    """第 N 套 = 先点 N 次「下一套」再点「一键采用」。"""
    clicked = []

    monkeypatch.setattr(mimengzhiyu, "find_center_silent",
                        lambda path, *a, **k: (10, 10))
    monkeypatch.setattr(mimengzhiyu, "send_coord",
                        lambda x, y, *a, **k: clicked.append(("coord", x, y)))
    monkeypatch.setattr(mimengzhiyu, "random_sleep", lambda *a, **k: None)

    def fake_wait(template_path, name, threshold=0.8, **kwargs):
        clicked.append(("wait", template_path))
        return True

    monkeypatch.setattr(mimengzhiyu, "wait_and_click", fake_wait)
    assert mimengzhiyu._adopt_ranked_lineup(2) is True

    next_clicks = [c for c in clicked if c[0] == "wait"
                   and c[1] == mimengzhiyu.tpl_lineup_next]
    assert len(next_clicks) == 2, clicked
    assert clicked[-1] == ("wait", mimengzhiyu.tpl_rank_adopt)


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
