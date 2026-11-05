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


def test_hud_fallback_returns_false_after_retries_with_exact_click_count(monkeypatch):
    """confirm 恒为假：retries 用尽返回 False，send_coord 精确调用 retries×2（每轮两次）。"""
    sent = []
    monkeypatch.setattr(hy, "game_client_region", lambda: (2000, 100, 1600, 900))
    monkeypatch.setattr(hy, "send_coord", lambda x, y: sent.append((x, y)))
    monkeypatch.setattr(hy, "time", _NO_SLEEP)
    monkeypatch.setattr(hy, "_friends_panel_visible", lambda: False)

    assert hy._open_friends_via_hud(retries=3) is False

    expected = (2000 + hy.FRIENDS_HUD_POS[0], 100 + hy.FRIENDS_HUD_POS[1])
    assert len(sent) == 3 * 2
    assert set(sent) == {expected}, "重试期间坐标不能漂移"


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


def _stub_friend_rewards(monkeypatch):
    """桩掉好友面板额外奖励的外部依赖，返回点击记录与弹窗清理次数。"""
    sent = []
    close_calls = []
    monkeypatch.setattr(hy, "send_coord", lambda x, y: sent.append((x, y)))
    monkeypatch.setattr(hy, "_close_popups", lambda *args, **kwargs: close_calls.append(1))
    monkeypatch.setattr(hy, "time", _NO_SLEEP)
    return sent, close_calls


def test_claim_friend_rewards_clicks_lingqu_and_chest(monkeypatch):
    """「领取」与满箱宝箱依次出现时都要点掉，每次点击后都清理弹窗。"""
    sent, close_calls = _stub_friend_rewards(monkeypatch)
    lingqu_results = iter([(3000, 800), None, None])
    baoxiang_results = iter([(2000, 500), None])

    def fake_find(template_path, *args, **kwargs):
        if template_path == hy.LINGQU:
            return next(lingqu_results, None)
        if template_path == hy.BAOXIANG_FULL:
            return next(baoxiang_results, None)
        return None

    monkeypatch.setattr(hy, "find_center", fake_find)

    assert hy._claim_friend_rewards() == 2
    assert sent == [(3000, 800), (2000, 500)]
    assert len(close_calls) == 2


def test_claim_friend_rewards_handles_shouhuo_popup(monkeypatch):
    """宝箱点开后弹出「收获奖励」时补点一次并清理弹窗。"""
    sent, close_calls = _stub_friend_rewards(monkeypatch)
    lingqu_results = iter([(3000, 800), None])
    shouhuo_results = iter([(2500, 600), None])

    def fake_find(template_path, *args, **kwargs):
        if template_path == hy.LINGQU:
            return next(lingqu_results, None)
        if template_path == hy.SHOUHUOJIANGJI:
            return next(shouhuo_results, None)
        return None

    monkeypatch.setattr(hy, "find_center", fake_find)

    assert hy._claim_friend_rewards() == 1
    assert sent == [(3000, 800), (2500, 600)]
    assert len(close_calls) == 2


def test_claim_friend_rewards_returns_zero_without_rewards(monkeypatch):
    """什么都找不到时直接返回 0，不能盲点。"""
    sent, _close_calls = _stub_friend_rewards(monkeypatch)
    monkeypatch.setattr(hy, "find_center", lambda *args, **kwargs: None)

    assert hy._claim_friend_rewards() == 0
    assert sent == []
