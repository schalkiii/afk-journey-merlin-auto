"""2026-11-26 实机两处修复的回归用例。

1. 翻翻乐：菜单项刚出现 0.1 秒就点「任务」，点击落到遮罩上把菜单一起关掉，随后
   补点「任务」永远找不到（失败现场停在主界面），整项 15 秒判失败。改为每轮从
   「菜单」重新开始。
2. 迷梦之域：误点玩家头像弹出资料卡后，「点击空白处关闭」只到 0.819，某帧低于 0.8
   时 `_ensure_mimeng_main` 三条分支全不命中、只剩 sleep，12 秒空转后判失败。
   改为兜底点一次左下空白。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fanfanle as ff
import hongbaolingqu
import mimengzhiyu as mm

# ===== 1. 翻翻乐：菜单被点关后要重新打开 =====

def _stub_enter(monkeypatch, panel_open_rounds):
    """跑 `_enter_fanfanle`：菜单每次都处于关闭态，第 N 轮起任务面板才算打开。"""
    menu_clicks = []
    recovered = {"count": 0}
    monkeypatch.setattr(ff.time, "sleep", lambda _seconds: None)

    def fake_wait_click(template_path, name, threshold=0.8, timeout=None, **kwargs):
        if template_path == ff.tpl_menu:
            menu_clicks.append(name)
        return True

    monkeypatch.setattr(ff, "wait_and_click", fake_wait_click)
    # 菜单没开（任务项找不到），页签与按钮都能找到
    monkeypatch.setattr(
        ff, "find_center_silent",
        lambda template_path, *args, **kwargs: (
            (300, 300)
            if template_path in (ff.tpl_fanfanle_tab_selected, ff.tpl_fanfanle_tab,
                                 ff.tpl_add_progress)
            else None
        ),
    )
    monkeypatch.setattr(ff, "click_position", lambda pos, **kwargs: None)
    monkeypatch.setattr(ff, "recover_to_main_interface",
                        lambda: recovered.__setitem__("count", recovered["count"] + 1))

    rounds = {"n": 0}

    def fake_panel_open():
        rounds["n"] += 1
        return rounds["n"] >= panel_open_rounds

    monkeypatch.setattr(hongbaolingqu, "_panel_open", fake_panel_open)
    return menu_clicks, recovered


def test_reopens_menu_after_task_click_closed_it(monkeypatch):
    """第一次点「任务」把菜单一起关掉，第二轮必须重新点「菜单」再点「任务」。"""
    menu_clicks, _recovered = _stub_enter(monkeypatch, panel_open_rounds=2)

    assert ff._enter_fanfanle() is True
    assert len(menu_clicks) == 2


def test_gives_up_after_two_menu_rounds(monkeypatch):
    """两轮都打不开任务面板才判失败，并回退主界面。"""
    menu_clicks, recovered = _stub_enter(monkeypatch, panel_open_rounds=99)

    assert ff._enter_fanfanle() is False
    assert len(menu_clicks) == 2
    assert recovered["count"] == 1


# ===== 2. 迷梦之域：认不出关闭提示时兜底点空白 =====

def test_ensure_mimeng_main_clicks_blank_when_popup_unmatched(monkeypatch):
    """资料卡上的关闭提示只到 0.79 也要能关掉：兜底空白点击后应重新看到「挑战」。"""
    blank_clicks = {"n": 0}
    state = {"challenge": False}
    monkeypatch.setattr(mm.time, "sleep", lambda _seconds: None)

    def fake_find(template_path, threshold=0.8, timeout=None, **kwargs):
        if template_path == mm.tpl_tiaozhan:
            return (800, 800) if state["challenge"] else None
        return None   # 「点击空白处关闭」/exitck/exit 全认不出

    monkeypatch.setattr(mm, "find_center_silent", fake_find)
    monkeypatch.setattr(mm, "wait_and_click", lambda *args, **kwargs: False)
    monkeypatch.setattr(mm, "dismiss_popup_away_from", lambda: False)

    def fake_blank_click():
        blank_clicks["n"] += 1
        state["challenge"] = True   # 空白点击关掉了资料卡

    monkeypatch.setattr(mm, "click_blank_to_exit", fake_blank_click)

    assert mm._ensure_mimeng_main(timeout=5.0) is True
    assert blank_clicks["n"] == 1
