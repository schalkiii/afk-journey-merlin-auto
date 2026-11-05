"""迷梦之域右上角奖励领取与退出兜底的单元测试（不接触真实游戏）。

模板匹配、点击、等待、关弹窗与主界面判定全部在模块级接缝打桩，
只验证区域探测顺序、点击次数以及「flow_return_main 后再兜底恢复」的顺序契约。
"""
import mimengzhiyu as mm


def _stub_claim_seams(monkeypatch, hits):
    """桩掉领取接缝；hits 是 {client_region: (template_path, pos)}，返回调用记账。"""
    clicks, waits, closes, finds = [], [], [], []

    def fake_find(template_path, threshold=0.8, region=None, timeout=0,
                  interval=0.5, client_region=None):
        finds.append((template_path, client_region))
        hit = hits.get(client_region)
        if hit and hit[0] == template_path:
            return hit[1]
        return None

    def fake_click(pos, wait=1.5, twice=True):
        clicks.append((pos, wait, twice))
        return True

    def fake_wait_click(template_path, name, threshold=0.8, timeout=None, **kwargs):
        waits.append((template_path, name, timeout))
        return True

    monkeypatch.setattr(mm, "find_center_silent", fake_find)
    monkeypatch.setattr(mm, "click_position", fake_click)
    monkeypatch.setattr(mm, "wait_and_click", fake_wait_click)
    monkeypatch.setattr(mm, "dismiss_popup_away_from", lambda: closes.append("close"))
    monkeypatch.setattr(mm, "log", lambda *args, **kwargs: None)
    return clicks, waits, closes, finds


CHEST_HIT = (mm.tpl_baoxiang_full, (1500, 120))


def test_claim_top_right_chest_clicks_harvest_and_closes(monkeypatch):
    """右上角命中宝箱：点一次宝箱 → 点「收获奖励」→ 关弹窗，返回 True。"""
    clicks, waits, closes, finds = _stub_claim_seams(
        monkeypatch, {mm.MIMENG_TOP_RIGHT_REGION: CHEST_HIT}
    )

    assert mm._claim_top_right_reward() is True

    assert finds == [(mm.tpl_baoxiang_full, mm.MIMENG_TOP_RIGHT_REGION)]
    assert clicks == [((1500, 120), 1.5, False)]
    assert waits == [(mm.tpl_shouhuojiangli, "shouhuojiangli(右上角)", 2.0)]
    assert closes == ["close"]


def test_claim_top_right_returns_false_without_click_when_nothing_found(monkeypatch):
    """三种模板都没命中：返回 False，且不得点击、不得关弹窗，不影响后续挑战。"""
    clicks, waits, closes, finds = _stub_claim_seams(monkeypatch, {})

    assert mm._claim_top_right_reward() is False

    assert clicks == []
    assert waits == []
    assert closes == []
    assert [template for template, _region in finds] == [
        mm.tpl_baoxiang_full,
        mm.tpl_lingqu,
        mm.tpl_yijianlingqu,
    ]


def test_exit_to_main_recovers_after_flow_return_main(monkeypatch):
    """退出路径顺序契约：先 flow_return_main，仍未回主界面才调 recover_to_main_interface。"""
    calls = []

    monkeypatch.setattr(mm, "flow_return_main",
                        lambda: calls.append("flow_return_main") or False)
    monkeypatch.setattr(mm, "at_main_interface", lambda: False)
    monkeypatch.setattr(
        mm, "recover_to_main_interface",
        lambda *args, **kwargs: calls.append("recover") or True,
    )
    monkeypatch.setattr(mm, "log", lambda *args, **kwargs: None)

    assert mm._exit_to_main() is True
    assert calls == ["flow_return_main", "recover"]


def test_exit_to_main_skips_recover_when_already_at_main(monkeypatch):
    """flow_return_main 后已确认在主界面：不再重复调用兜底恢复。"""
    calls = []

    monkeypatch.setattr(mm, "flow_return_main",
                        lambda: calls.append("flow_return_main") or True)
    monkeypatch.setattr(mm, "at_main_interface", lambda: True)
    monkeypatch.setattr(
        mm, "recover_to_main_interface",
        lambda *args, **kwargs: calls.append("recover") or True,
    )
    monkeypatch.setattr(mm, "log", lambda *args, **kwargs: None)

    assert mm._exit_to_main() is True
    assert calls == ["flow_return_main"]


def test_handle_battle_failure_falls_back_to_main_without_changing_result(monkeypatch):
    """「未能确认回到挑战界面」的战斗失败分支：补兜底恢复，但返回值仍为 False。"""
    calls = []

    monkeypatch.setattr(
        mm, "find_center_silent",
        lambda template_path, threshold=0.8, **kwargs: (
            (900, 500) if template_path == mm.tpl_tiaoguozhandou else None
        ),
    )
    monkeypatch.setattr(mm, "send_coord", lambda x, y: calls.append("click"))
    monkeypatch.setattr(mm, "random_sleep", lambda: None)
    monkeypatch.setattr(mm, "wait_and_click", lambda *args, **kwargs: True)
    monkeypatch.setattr(mm, "close_result_popups", lambda: False)
    monkeypatch.setattr(mm, "at_main_interface", lambda: False)
    monkeypatch.setattr(
        mm, "recover_to_main_interface",
        lambda *args, **kwargs: calls.append("recover") or True,
    )
    monkeypatch.setattr(mm, "log", lambda *args, **kwargs: None)

    assert mm.handle_battle() is False
    assert calls.count("recover") == 1


def test_flow_claims_top_right_after_entering_mimeng(monkeypatch):
    """进入迷梦之域界面后、主循环前先领右上角奖励（用 challenge_count=0 走短路径验证）。"""
    order = []

    def fake_wait_click(template_path, name, *args, **kwargs):
        order.append(name)
        return True

    monkeypatch.setattr(mm, "wait_and_click", fake_wait_click)
    monkeypatch.setattr(mm, "random_sleep", lambda: None)
    monkeypatch.setattr(mm, "_claim_top_right_reward",
                        lambda: order.append("claim") or True)
    monkeypatch.setattr(mm, "check_and_handle_libao", lambda: None)
    monkeypatch.setattr(mm, "close_result_popups", lambda: True)
    monkeypatch.setattr(mm, "flow_return_main",
                        lambda: order.append("flow_return_main") or True)
    monkeypatch.setattr(mm, "at_main_interface", lambda: True)

    assert mm.flow_mimengzhiyu(challenge_count=0) is True
    assert order == ["wanfamulu", "mimengzhiyu", "claim", "exit", "flow_return_main"]
