"""推图「赛季阶段排名 → 首通奖励」领取链路的单元测试。"""
import push


def test_claim_first_clear_returns_true_only_with_reward_popup(monkeypatch):
    """标题都确认到、一键领取命中且弹出获得奖励时返回 True，并原路返回。"""
    clicks = []
    monkeypatch.setattr(push, "game_client_region", lambda *a, **k: (100, 50, 1600, 900))
    monkeypatch.setattr(push, "click_position",
                        lambda pos, wait=1.5, twice=False: clicks.append(pos))
    monkeypatch.setattr(
        push, "find_center_silent",
        lambda template_path, threshold=0.8, timeout=0, **kwargs: (
            (300, 300) if template_path in (push.tpl_rank_title, push.tpl_first_clear,
                                            push.tpl_reward_popup) else None
        ),
    )
    monkeypatch.setattr(push, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(push, "dismiss_popup_away_from", lambda: clicks.append("close"))

    assert push.claim_first_clear_reward() is True
    # 奖杯 → 首通图标 → 关弹窗 → 两次返回
    assert clicks[0] == (1665, 95)
    assert clicks[1] == (1300, 195)
    assert "close" in clicks


def test_claim_first_clear_returns_false_when_rank_not_open(monkeypatch):
    """奖杯点不开赛季阶段排名时直接跳过，不点首通图标。"""
    clicks = []
    monkeypatch.setattr(push, "game_client_region", lambda *a, **k: (100, 50, 1600, 900))
    monkeypatch.setattr(push, "click_position",
                        lambda pos, wait=1.5, twice=False: clicks.append(pos))
    monkeypatch.setattr(push, "find_center_silent", lambda *a, **k: None)

    assert push.claim_first_clear_reward() is False
    assert clicks == [(1665, 95), (1665, 95)]
