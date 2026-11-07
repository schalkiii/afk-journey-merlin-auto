"""迷梦之域右上角奖励领取与退出兜底的单元测试（不接触真实游戏）。

模板匹配、点击、等待、关弹窗与主界面判定全部在模块级接缝打桩，
只验证区域探测顺序、点击次数以及「flow_return_main 后再兜底恢复」的顺序契约。
"""
import mimengzhiyu as mm


def _stub_claim_seams(monkeypatch, hits, rank_panel=False, rank_reward=False):
    """桩掉领取接缝；hits 是 {client_region: (template_path, pos)}，返回调用记账。

    rank_panel / rank_reward 控制「排行榜礼包」这条新链路：前者表示排行榜面板能打开，
    后者表示点礼包后直接弹出「获得奖励」。两者都为 False 时走旧的右上角探测分支。
    """
    clicks, waits, closes, finds = [], [], [], []

    def fake_find(template_path, threshold=0.8, region=None, timeout=0,
                  interval=0.5, client_region=None):
        finds.append((template_path, client_region))
        if template_path == mm.tpl_mimeng_rank:
            return (100, 100) if rank_panel else None
        if template_path == mm.tpl_huodejiangli:
            return (200, 200) if rank_reward else None
        # 挑战按钮可见 = 已回到迷梦主界面，让新增的 _ensure_mimeng_main 立即收敛
        if template_path == mm.tpl_tiaozhan:
            return (300, 300)
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
    monkeypatch.setattr(mm, "game_client_region", lambda *a, **k: (1000, 500, 1600, 900))
    monkeypatch.setattr(mm, "dismiss_popup_away_from", lambda: closes.append("close"))
    monkeypatch.setattr(mm, "log", lambda *args, **kwargs: None)
    return clicks, waits, closes, finds


CHEST_HIT = (mm.tpl_baoxiang_full, (1500, 120))


def test_claim_top_right_chest_clicks_harvest_and_closes(monkeypatch):
    """排行榜无礼包时回退到右上角宝箱：点宝箱 → 点「收获奖励」→ 关弹窗，返回 True。"""
    clicks, waits, closes, finds = _stub_claim_seams(
        monkeypatch, {mm.MIMENG_TOP_RIGHT_REGION: CHEST_HIT}
    )

    assert mm._claim_top_right_reward() is True

    # 先点右侧「排行榜」入口，确认打不开后才走旧的右上角区域探测
    assert clicks[0] == ((2216, 590), 1.5, False)
    assert finds[0] == (mm.tpl_mimeng_rank, None)
    assert finds[1] == (mm.tpl_baoxiang_full, mm.MIMENG_TOP_RIGHT_REGION)
    assert clicks[1] == ((1500, 120), 1.5, False)
    assert waits == [(mm.tpl_shouhuojiangli, "shouhuojiangli(右上角)", 2.0)]
    assert closes == ["close"]


def test_claim_rank_gift_clicks_popup_and_returns(monkeypatch):
    """排行榜可打开且礼包直接弹「获得奖励」：领到并原路返回。"""
    clicks, waits, closes, finds = _stub_claim_seams(
        monkeypatch, {}, rank_panel=True, rank_reward=True
    )

    assert mm._claim_top_right_reward() is True

    assert clicks[0] == ((2216, 590), 1.5, False)   # 排行榜入口
    assert clicks[1] == ((2163, 562), 1.2, False)   # 右上角礼包
    assert closes == ["close"]
    # 领完后统一走 _ensure_mimeng_main：挑战按钮已可见即收敛，不再单独发 exitck
    assert waits == []
    assert (mm.tpl_tiaozhan, None) in finds
    # 领到之后不再走旧的右上角区域探测
    assert all(region is None for _tpl, region in finds)


def test_claim_top_right_returns_false_when_nothing_found(monkeypatch):
    """排行榜与三种右上角模板都没命中：返回 False，且不点任何奖励、不关弹窗。"""
    clicks, waits, closes, finds = _stub_claim_seams(monkeypatch, {})

    assert mm._claim_top_right_reward() is False

    # 只有「排行榜」入口这一次点击（它是无害的界面跳转），没有任何奖励点击
    assert clicks == [((2216, 590), 1.5, False)]
    assert waits == []
    assert closes == []
    assert [template for template, _region in finds] == [
        mm.tpl_mimeng_rank,
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
    state = {"skipped": False}

    def fake_find(template_path, threshold=0.8, **kwargs):
        # 先识别「跳过战斗」并点一次；之后战斗结束回到迷梦主界面（挑战按钮重新可见），
        # 不弹「竞技场结算」——即 2026-11-07 实机的新结束方式。
        if template_path == mm.tpl_tiaoguozhandou and not state["skipped"]:
            state["skipped"] = True
            return (900, 500)
        if template_path == mm.tpl_tiaozhan and state["skipped"]:
            return (700, 900)
        return None

    monkeypatch.setattr(mm, "find_center_silent", fake_find)
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
    # 进玩法目录已收敛到 common.open_wanfamulu（点后确认目录标题）；沿用同名事件记账
    monkeypatch.setattr(mm, "open_wanfamulu",
                        lambda *args, **kwargs: (order.append("wanfamulu"), True)[1])
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
