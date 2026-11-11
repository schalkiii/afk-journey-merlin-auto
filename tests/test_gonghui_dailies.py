"""流程模块的决策逻辑测试：返回主界面委托、公会玩法入口、公会日常次数上限。

全部在模块级接缝打桩，不接触真实游戏。负验证留痕：
- 把 `flow_enter_guild_play` 里「卡片点击后目录仍在则补点」的循环删掉，
  `test_guild_card_click_retries_when_catalog_stays` 必须失败；
- 把 `_wait_any` 改成统一阈值（忽略每个模板各自的阈值），
  `test_wait_any_passes_per_template_threshold` 必须失败；
- 把 `_use_own_searches` / `_join_others` 的次数上限去掉，两条上限用例必须失败。
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flow_enter
import flow_gonghui
import jieshezhanxian
import lieshouxunshang


class _FakeTime:
    def __init__(self):
        self.elapsed = 0.0

    def sleep(self, seconds):
        self.elapsed += seconds

    def time(self):
        return self.elapsed


@pytest.fixture
def fake_time(monkeypatch):
    clock = _FakeTime()
    for module in (flow_gonghui, jieshezhanxian, lieshouxunshang):
        monkeypatch.setattr(module, "time", clock)
        monkeypatch.setattr(module, "check_stop", lambda: None)
        monkeypatch.setattr(module, "log", lambda *_a, **_k: None)
    return clock


def test_flow_return_main_delegates_with_max_tries(monkeypatch):
    seen = []
    monkeypatch.setattr(flow_enter, "recover_to_main_interface",
                        lambda **kwargs: seen.append(kwargs) or True)
    assert flow_enter.flow_return_main(max_tries=3) is True
    assert seen == [{"max_tries": 3}]


def _stub_guild(monkeypatch, *, catalog_open=True, active=True, tab=True,
                card=True, catalog_after_clicks):
    """按模板返回命中坐标；catalog_after_clicks 依次给出每次点卡片后目录标题是否还在。"""
    calls = types.SimpleNamespace(clicks=[], finds=[], scrolls=0)
    after = list(catalog_after_clicks)

    def fake_find(template, *args, **kwargs):
        calls.finds.append(template)
        if template == flow_gonghui.tpl_tab_active:
            return (100, 100) if active else None
        if template == flow_gonghui.tpl_tab:
            return (110, 110) if tab else None
        if template == flow_gonghui.tpl_catalog_title:
            return (120, 120) if (after.pop(0) if after else False) else None
        if template == "card.png":
            return (200, 200) if card else None
        return None

    def fake_scroll(*args, **kwargs):
        calls.scrolls += 1
        return True

    monkeypatch.setattr(flow_gonghui, "open_wanfamulu", lambda **_k: catalog_open)
    monkeypatch.setattr(flow_gonghui, "find_center_silent", fake_find)
    monkeypatch.setattr(flow_gonghui, "scroll_in_client_region", fake_scroll)
    monkeypatch.setattr(flow_gonghui, "click_position",
                        lambda pos, *a, **k: calls.clicks.append(pos))
    return calls


def test_guild_entry_fails_when_catalog_not_open(monkeypatch, fake_time):
    calls = _stub_guild(monkeypatch, catalog_open=False, catalog_after_clicks=[])
    assert flow_gonghui.flow_enter_guild_play("card.png", "结社战线") is False
    assert calls.clicks == []


def test_guild_active_tab_skips_tab_click(monkeypatch, fake_time):
    calls = _stub_guild(monkeypatch, active=True, catalog_after_clicks=[False])
    assert flow_gonghui.flow_enter_guild_play("card.png", "结社战线") is True
    assert (110, 110) not in calls.clicks, "页签已激活时不应再点未激活页签"
    assert calls.clicks == [(200, 200)]


def test_guild_inactive_tab_clicks_tab_then_card(monkeypatch, fake_time):
    calls = _stub_guild(monkeypatch, active=False, catalog_after_clicks=[False])
    assert flow_gonghui.flow_enter_guild_play("card.png", "狩猎悬赏") is True
    assert calls.clicks == [(110, 110), (200, 200)]


def test_guild_card_click_retries_when_catalog_stays(monkeypatch, fake_time):
    calls = _stub_guild(monkeypatch, active=True, catalog_after_clicks=[True, False])
    assert flow_gonghui.flow_enter_guild_play("card.png", "结社战线") is True
    assert calls.clicks == [(200, 200), (200, 200)], "目录仍在说明点击被吞，必须补点一次"


def test_guild_reports_missing_card(monkeypatch, fake_time):
    _stub_guild(monkeypatch, active=True, card=False, catalog_after_clicks=[])
    assert flow_gonghui.flow_enter_guild_play("card.png", "结社战线") is False


def test_wait_any_passes_per_template_threshold(monkeypatch, fake_time):
    seen = []

    def fake_find(template, threshold, *args, **kwargs):
        seen.append((template, threshold))
        return (10, 10) if template == "win.png" else None

    monkeypatch.setattr(jieshezhanxian, "_find", fake_find)
    result = jieshezhanxian._wait_any([("lose.png", 0.85), ("win.png", 0.9)], timeout=2)
    assert result == ("win.png", (10, 10))
    assert ("lose.png", 0.85) in seen and ("win.png", 0.9) in seen


def test_wait_any_times_out(monkeypatch, fake_time):
    monkeypatch.setattr(jieshezhanxian, "_find", lambda *_a, **_k: None)
    assert jieshezhanxian._wait_any([("any.png", 0.8)], timeout=0.5) == (None, None)


def test_click_and_expect_retries_until_expected_screen(monkeypatch, fake_time):
    clicks = []
    calls = {"n": 0}

    def fake_find(template, *args, **kwargs):
        if template == "battle.png":
            return (1, 1)
        calls["n"] += 1
        return (2, 2) if calls["n"] >= 2 else None

    monkeypatch.setattr(jieshezhanxian, "_find", fake_find)
    monkeypatch.setattr(jieshezhanxian, "click_position",
                        lambda pos, *a, **k: clicks.append(pos))
    assert jieshezhanxian._click_and_expect("battle.png", "settle.png") is True
    assert len(clicks) == 2


def test_use_own_searches_stops_at_cap(monkeypatch, fake_time):
    monkeypatch.setattr(lieshouxunshang, "_find", lambda *_a, **_k: (1, 1))
    monkeypatch.setattr(lieshouxunshang, "_close_settlements", lambda: True)
    monkeypatch.setattr(lieshouxunshang, "click_position", lambda *_a, **_k: None)
    assert lieshouxunshang._use_own_searches() == lieshouxunshang.MAX_SEARCHES


def test_use_own_searches_stops_when_settlement_stuck(monkeypatch, fake_time):
    monkeypatch.setattr(lieshouxunshang, "_find", lambda *_a, **_k: (1, 1))
    monkeypatch.setattr(lieshouxunshang, "_close_settlements", lambda: False)
    monkeypatch.setattr(lieshouxunshang, "click_position", lambda *_a, **_k: None)
    assert lieshouxunshang._use_own_searches() == 1


def test_join_others_stops_at_daily_cap(monkeypatch, fake_time):
    monkeypatch.setattr(lieshouxunshang, "_find", lambda *_a, **_k: (100, 100))
    monkeypatch.setattr(lieshouxunshang, "find_center_silent", lambda *_a, **_k: (1, 1))
    monkeypatch.setattr(lieshouxunshang, "click_position", lambda *_a, **_k: None)
    assert lieshouxunshang._join_others() == lieshouxunshang.MAX_JOINS


def test_join_others_skips_outside_panel(monkeypatch, fake_time):
    monkeypatch.setattr(lieshouxunshang, "_find", lambda *_a, **_k: None)
    assert lieshouxunshang._join_others() == 0


def test_join_others_scrolls_then_finds_join(monkeypatch, fake_time):
    """没找到「加入」时先滚到底再找（2026-11-08 用户反馈：有卡片折叠在列表下方）。"""
    scroll_calls = []
    # 顺序：面板标题 → 两次没找到「加入」→ 滚动后三次找到（MAX_JOINS=3）
    results = [(100, 100), None, None, (1, 1), (1, 1), (1, 1)]

    def fake_find(_tpl, *args, **kwargs):
        return results.pop(0) if results else None

    monkeypatch.setattr(lieshouxunshang, "find_center_silent", fake_find)
    monkeypatch.setattr(lieshouxunshang, "scroll_in_client_region",
                        lambda *a, **k: scroll_calls.append(True) or True)
    monkeypatch.setattr(lieshouxunshang, "click_position", lambda *a, **k: True)
    monkeypatch.setattr(lieshouxunshang, "check_stop", lambda: None)
    monkeypatch.setattr(lieshouxunshang, "log", lambda *a, **k: None)

    assert lieshouxunshang._join_others() == 3
    assert len(scroll_calls) >= 1, "找不到「加入」时必须滚动列表"
