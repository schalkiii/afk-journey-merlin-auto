"""2026-11-27 实机修复的回归用例。

推图：首通奖励返回时，「赛季阶段排名」面板关闭有约 1 秒动画。旧实现只要标题还命中
就补点 exitck，今天连点三次直接退回玩法目录，随后 15 秒找不到「挑战」、15 秒找不到
exit，推图整项 59 秒判失败（失败现场就是玩法目录卡片）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import push


def _stub_claim(monkeypatch, closing_polls):
    """最短路径跑 `claim_first_clear_reward`：无首通可领项，只看返回阶段点了几次。

    `closing_polls` 模拟面板关闭动画：点完 exit 后，标题还会继续命中这么多次
    （None=一直关不掉）。旧实现只查一次就开始补点，必然把下面一层的返回也点掉。
    """
    clicks = []
    state = {"remaining": None, "title_checked": False}
    monkeypatch.setattr(push, "game_client_region", lambda: (0, 0, 1600, 900))
    monkeypatch.setattr(push.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(push, "click_position",
                        lambda pos, **kwargs: clicks.append(("click", pos)))

    def fake_find(template_path, threshold=0.8, timeout=0.0, **kwargs):
        if template_path == push.tpl_rank_title:
            if not state["title_checked"]:
                state["title_checked"] = True   # 第一次是「奖杯打开排名面板」的确认
                return (100, 100)
            if state["remaining"] is None:
                return (100, 100)               # 一直关不掉
            if state["remaining"] <= 0:
                return None
            state["remaining"] -= 1
            return (100, 100)
        if template_path == push.tpl_first_clear:
            return (200, 200)
        return None

    def fake_wait_click(template_path, name, *args, **kwargs):
        clicks.append(name)
        if name == "exit(shoutong)":
            state["remaining"] = closing_polls
        return True

    monkeypatch.setattr(push, "find_center_silent", fake_find)
    monkeypatch.setattr(push, "wait_and_click", fake_wait_click)
    return clicks


def test_first_clear_does_not_back_click_twice(monkeypatch):
    """标题在关闭动画里还会命中几次：等它真的消失，不能立刻补点把下一层返回也点掉。"""
    clicks = _stub_claim(monkeypatch, closing_polls=3)

    assert push.claim_first_clear_reward() is False   # 没有可领项
    assert "exit(shoutong)" in clicks
    assert not any(str(name).startswith("exitck(rank)") for name in clicks)


def test_first_clear_backs_out_when_panel_really_stuck(monkeypatch):
    """标题一直不消失（面板真没关掉）时仍要补点 exitck，保留 11-18 的兜底。"""
    clicks = _stub_claim(monkeypatch, closing_polls=None)

    assert push.claim_first_clear_reward() is False
    assert sum(1 for name in clicks if str(name).startswith("exitck(rank)")) == 2
