"""好友奖励：赠礼点击循环与 HUD 兜底入口（不接触真实游戏）。

实测依据：点一次「一键赠礼并收取」当天就赠完并收完（按钮变灰），收礼进度满 10 的宝箱
自动入账；主界面右下角好友图标是好友面板的直达入口，用作 菜单→社交 失败时的兜底。
"""
import types

import haoyoujiangli as hy

_NO_SLEEP = types.SimpleNamespace(sleep=lambda *args: None)


def test_collect_gifts_clicks_until_button_gone(monkeypatch):
    sent = []
    positions = iter([(3000, 800), (3000, 800), None])
    monkeypatch.setattr(hy, "find_center", lambda *args, **kwargs: next(positions))
    monkeypatch.setattr(hy, "send_coord", lambda x, y: sent.append((x, y)))
    monkeypatch.setattr(hy, "_close_popups", lambda *args, **kwargs: None)
    monkeypatch.setattr(hy, "time", _NO_SLEEP)

    assert hy._collect_gifts() == 2
    assert sent == [(3000, 800), (3000, 800)]


def test_collect_gifts_capped_when_button_never_gone(monkeypatch):
    """界面刷新不出来时靠上限退出，不能死循环点同一个按钮。"""
    monkeypatch.setattr(hy, "find_center", lambda *args, **kwargs: (3000, 800))
    monkeypatch.setattr(hy, "send_coord", lambda x, y: None)
    monkeypatch.setattr(hy, "_close_popups", lambda *args, **kwargs: None)
    monkeypatch.setattr(hy, "time", _NO_SLEEP)

    assert hy._collect_gifts() == hy.MAX_GIFT_CLICKS


def test_hud_fallback_adds_client_origin_and_confirms_panel(monkeypatch):
    """兜底入口：坐标必须是「客户区原点 + 偏移」的整屏坐标，且要点两次（首次被激活吞掉）。"""
    clicks = []
    monkeypatch.setattr(hy, "game_client_region", lambda: (2000, 100, 1600, 900))
    monkeypatch.setattr(hy, "send_coord", lambda x, y: clicks.append((x, y)))
    monkeypatch.setattr(hy, "time", _NO_SLEEP)
    visible = iter([False, True])
    monkeypatch.setattr(hy, "_friends_panel_visible", lambda: next(visible))

    assert hy._open_friends_via_hud() is True

    expected = (2000 + hy.FRIENDS_HUD_POS[0], 100 + hy.FRIENDS_HUD_POS[1])
    assert clicks[0] == expected, "把客户区坐标当整屏坐标传进去就会点到别处"
    # 每轮连点两下（窗口未前台时第一次被激活吞掉）；第一轮没确认到面板，所以共两轮四次
    assert len(clicks) == 4
    assert set(clicks) == {expected}, "重试只能重复同一个入口，不能漂到别的坐标"
