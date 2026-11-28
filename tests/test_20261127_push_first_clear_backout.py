"""推图首通奖励返回阶段的回归用例（2026-11-27 起，2026-11-28 升级判据）。

11-27：只要「赛季阶段排名」标题还命中就补点 exitck，连点三次退回玩法目录，推图失败。
11-28：改成「等标题消失」后仍然失败——标题模板在关闭动画里会间歇丢失，2 秒没认出
就以为退完了，其实还停在排名面板上，随后找不到「挑战」，整项 36 秒判失败。
现在改为以「是否回到推图页面（挑战 / 幻灵挑战）」为目标状态判断。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import push


def _stub_claim(monkeypatch, exit_reaches_push_page):
    """最短路径跑 `claim_first_clear_reward`：无首通可领项，只看返回阶段点了几次。

    `exit_reaches_push_page=True` 模拟 exit 一次就回到推图页；
    False 模拟仍然停在排名面板（需要补点 exitck）。
    """
    clicks = []
    state = {"back": False, "title_checked": False}
    anchors = (push.tpl_tiaozhan, push.tpl_tiaozhanonly, push.tpl_huanlingcha)
    monkeypatch.setattr(push, "game_client_region", lambda: (0, 0, 1600, 900))
    monkeypatch.setattr(push.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(push, "click_position",
                        lambda pos, **kwargs: clicks.append(("click", pos)))

    def fake_find(template_path, threshold=0.8, timeout=0.0, **kwargs):
        if template_path == push.tpl_rank_title:
            if not state["title_checked"]:
                state["title_checked"] = True   # 第一次是「奖杯打开排名面板」的确认
                return (100, 100)
            return None
        if template_path == push.tpl_first_clear:
            return (200, 200)
        if template_path in anchors:
            return (300, 300) if state["back"] else None
        return None

    def fake_wait_click(template_path, name, *args, **kwargs):
        clicks.append(name)
        if name == "exit(shoutong)" and exit_reaches_push_page:
            state["back"] = True
        return True

    monkeypatch.setattr(push, "find_center_silent", fake_find)
    monkeypatch.setattr(push, "wait_and_click", fake_wait_click)
    return clicks


def test_first_clear_backs_to_push_page_without_extra_click(monkeypatch):
    """exit 一次就回到推图页：不能再补点 exitck，否则会退过头到玩法目录。"""
    clicks = _stub_claim(monkeypatch, exit_reaches_push_page=True)

    assert push.claim_first_clear_reward() is False   # 没有可领项
    assert "exit(shoutong)" in clicks
    assert not any(str(name).startswith("exitck(rank)") for name in clicks)


def test_first_clear_backs_out_until_push_page_visible(monkeypatch):
    """仍停在排名面板（推图页锚点不可见）时必须补点 exitck，直到回推图页或次数用尽。"""
    clicks = _stub_claim(monkeypatch, exit_reaches_push_page=False)

    assert push.claim_first_clear_reward() is False
    assert sum(1 for name in clicks if str(name).startswith("exitck(rank)")) == 3
