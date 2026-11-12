"""普竞战斗结束信号的回归测试：跳过与结算谁先出现就按谁走。

点完结算后还有一步「确认已经回到挑战界面」，走的是 `find_center_silent`（真实截屏）。
用例必须把它桩掉：否则结果取决于「这一刻游戏是否开着」——
2026-11-12 实测，游戏开着时这两条必失败（真实画面里没有挑战按钮 → 走进补点分支，
`sent` 多出两次点击），游戏关着时又因为每次要干等 8 秒超时而慢到 30 秒以上。
"""
import pujing


def _stub_back_to_challenge(monkeypatch):
    """把「回到挑战界面」的校验固定成「挑战按钮已出现」。"""
    monkeypatch.setattr(
        pujing, "find_center_silent",
        lambda tpl, *_a, **_k: (900, 500) if tpl == pujing.tpl_kaishitiaozhan else None,
    )


def test_battle_flow_accepts_direct_result_without_skip(monkeypatch):
    """战斗自动结束、没出现「跳过」时，直接识别结算不能判整轮失败。"""
    sent = []
    monkeypatch.setattr(pujing, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(
        pujing, "wait_for_any",
        lambda templates, **k: (pujing.tpl_pujingjieshu, "pujingjieshu", (900, 500)),
    )
    monkeypatch.setattr(pujing, "send_coord", lambda x, y: sent.append((x, y)))
    monkeypatch.setattr(pujing, "random_sleep", lambda: None)
    monkeypatch.setattr(pujing.time, "sleep", lambda _s: None)
    _stub_back_to_challenge(monkeypatch)

    assert pujing.execute_battle_flow(None, "battle", (100, 100)) is True
    # 战斗按钮一次 + 结算一次，且没有额外的跳过点击
    assert sent == [(100, 100), (900, 500)]


def test_battle_flow_clicks_skip_then_result(monkeypatch):
    """先出现「跳过」时仍按原链路：点跳过 → 等结算 → 点结算。"""
    sent = []
    monkeypatch.setattr(pujing, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(
        pujing, "wait_for_any",
        lambda templates, **k: (pujing.tpl_tiaoguo, "tiaoguo", (800, 400)),
    )
    monkeypatch.setattr(
        pujing, "wait_for_appearance",
        lambda *a, **k: (900, 500),
    )
    monkeypatch.setattr(pujing, "send_coord", lambda x, y: sent.append((x, y)))
    monkeypatch.setattr(pujing, "random_sleep", lambda: None)
    monkeypatch.setattr(pujing.time, "sleep", lambda _s: None)
    _stub_back_to_challenge(monkeypatch)

    assert pujing.execute_battle_flow(None, "battle", (100, 100)) is True
    assert sent == [(100, 100), (800, 400), (900, 500)]
