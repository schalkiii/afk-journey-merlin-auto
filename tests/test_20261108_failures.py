"""2026-11-08 实跑 5 个失败现场的回归用例（女神塔 / 爬塔 / 结社战线 / 狩猎悬赏 / 推图）。

失败现场证据见 `debug/failures/20261108-*` 与 `game_bot.log` 08:27–09:02 段：
- 女神塔：扫荡确认后停在扫荡面板，傻等「点击空白处关闭」15 秒超时 → 判失败；
- 爬塔：玩法目录已无「天穹试炼」卡片（活动下线），仍记 ✘ 失败；
- 结社战线 / 狩猎悬赏：入口卡片/招牌不可用（现场是家园视图），整任务判失败；
- 推图：点「自动挑战」被吞、按钮仍在，12 秒后判失败。

负验证留痕：
- 把 pata 的卡片缺失分支改成静默跳过（return True），`test_pata_fails_when_card_absent_after_scroll` 必须失败；
- 删掉 pata 的滚动重试，`test_pata_scrolls_then_finds_card` 必须失败；
- 删掉扫荡确认补点循环，`test_saodang_retries_confirm_when_button_stays` 必须失败；
- 把扫荡结果弹窗改回「必须点到否则失败」，`test_saodang_succeeds_without_result_popup` 必须失败；
- 删掉 start_battle 的补点重试，`test_start_battle_retries_when_button_stays` 必须失败；
- 删掉 flow_gonghui 的重开目录重试，`test_guild_play_reopens_catalog_when_closed` 必须失败；
- 把两个 main 的入口失败分支改回 `return False`，两条 skip 用例必须失败；
- 删掉普竞 zhandou 补点，`test_pujing_retries_zhandou_when_battle_button_stays` 必须失败；
- 把普竞/巅峰的「单场失败继续」改回 break/return False，两条 continue 用例必须失败。
"""

import time
import types

import flow_gonghui
import jieshezhanxian
import lieshouxunshang
import nvshenta as nt
import pata
import push

# ---------- 爬塔：卡片在列表下方，需滚动后查找 ----------

def test_pata_fails_when_card_absent_after_scroll(monkeypatch):
    """滚动后仍找不到卡片是异常：返回 False 让上层记失败，而不是静默跳过。

    2026-11-08 用户更正：天穹试炼没下线，只是在玩法目录里需要下滑才看得到。
    """
    calls = []

    monkeypatch.setattr(pata, "recover_to_main_interface", lambda *a, **k: True)
    monkeypatch.setattr(pata, "open_wanfamulu", lambda *a, **k: True)
    monkeypatch.setattr(pata, "find_center_silent", lambda *a, **k: None)
    monkeypatch.setattr(pata, "scroll_in_client_region",
                        lambda *a, **k: calls.append("scroll") or True)
    monkeypatch.setattr(pata, "random_sleep", lambda: None)
    # 2026-11-10：卡片点击改走 click_and_confirm（点后校验是否离开玩法目录）
    monkeypatch.setattr(pata, "click_and_confirm", lambda *a, **k: True)
    monkeypatch.setattr(pata, "time", types.SimpleNamespace(time=time.time,
                                                            sleep=lambda _s: None))

    assert pata.flow_pata() is False
    assert "scroll" in calls, "首屏没卡片必须先滚动再判定失败"


def test_pata_scrolls_then_finds_card(monkeypatch):
    """首屏没卡片、滚动后找到：正常进入并继续走完（塔都跳过时返回 True）。"""
    scroll_calls = []
    card_hits = [None, (1, 1)]

    def fake_find(tpl, *args, **kwargs):
        if tpl == pata.tpl_pata:
            return card_hits.pop(0) if card_hits else None
        return None   # 各塔都不存在，直接跳过

    monkeypatch.setattr(pata, "recover_to_main_interface", lambda *a, **k: True)
    monkeypatch.setattr(pata, "open_wanfamulu", lambda *a, **k: True)
    monkeypatch.setattr(pata, "find_center_silent", fake_find)
    monkeypatch.setattr(pata, "scroll_in_client_region",
                        lambda *a, **k: scroll_calls.append(True) or True)
    monkeypatch.setattr(pata, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(pata, "random_sleep", lambda: None)
    # 2026-11-10：卡片点击改走 click_and_confirm（点后校验是否离开玩法目录）
    monkeypatch.setattr(pata, "click_and_confirm", lambda *a, **k: True)
    monkeypatch.setattr(pata, "time", types.SimpleNamespace(time=time.time,
                                                            sleep=lambda _s: None))

    assert pata.flow_pata() is True
    assert len(scroll_calls) == 1


# ---------- 女神塔：扫荡确认补点 + 结果弹窗可选 ----------

def _stub_saodang(monkeypatch, saodang_button_persists):
    """saodang_button_persists=False 表示点击确认后按钮消失（扫荡已开始）。"""
    state = {"confirm": 0, "visible": True}
    clicks = []

    def fake_find(tpl, *args, **kwargs):
        if tpl == nt.tpl_nvshentasaodang:
            return (1, 1) if state["visible"] else None
        if tpl == nt.tpl_nvshentasaodangmax:
            return (1, 1)
        return None

    def fake_wait_and_click(_tpl, name, *args, **kwargs):
        clicks.append(name)
        if "confirm" in name:
            state["confirm"] += 1
            if not saodang_button_persists:
                state["visible"] = False
        return True

    monkeypatch.setattr(nt, "find_center_silent", fake_find)
    monkeypatch.setattr(nt, "wait_and_click", fake_wait_and_click)
    monkeypatch.setattr(nt, "random_sleep", lambda: None)
    monkeypatch.setattr(nt, "check_and_handle_libao", lambda *a, **k: None)
    return state, clicks


def test_saodang_retries_confirm_when_button_stays(monkeypatch):
    _state, clicks = _stub_saodang(monkeypatch, saodang_button_persists=True)

    assert nt.do_saodang_and_exit() is True
    assert sum(1 for name in clicks if "nvshentasaodang_confirm" in name) == 2
    assert "exit_final" in clicks


def test_saodang_succeeds_without_result_popup(monkeypatch):
    """扫荡后无结果弹窗（2026-11-08 实测）：不许再卡在等弹窗，直接退出成功。"""
    _state, clicks = _stub_saodang(monkeypatch, saodang_button_persists=False)

    assert nt.do_saodang_and_exit() is True
    assert sum(1 for name in clicks if "nvshentasaodang_confirm" in name) == 1
    assert "exit_final" in clicks


# ---------- 推图：自动挑战点击被吞时补点 ----------

def test_start_battle_retries_when_button_stays(monkeypatch):
    flow = push.PushFlow()
    clicks = []
    results = [None, push.tpl_zidongtiaozhanzhong]

    monkeypatch.setattr(push, "wait_and_click",
                        lambda _tpl, name, *a, **k: clicks.append(name) or True)
    monkeypatch.setattr(flow, "_wait_after_action",
                        lambda *a, **k: results.pop(0) if results else None)
    monkeypatch.setattr(push, "find_center_silent", lambda *a, **k: (1, 1))

    assert flow._st_start_battle() == push.STATE_MONITOR_BATTLE
    assert len(clicks) == 2


def test_start_battle_gives_up_when_button_gone(monkeypatch):
    """按钮已消失说明界面已切换：不再盲点，直接判失败。"""
    flow = push.PushFlow()
    clicks = []

    monkeypatch.setattr(push, "wait_and_click",
                        lambda _tpl, name, *a, **k: clicks.append(name) or True)
    monkeypatch.setattr(flow, "_wait_after_action", lambda *a, **k: None)
    monkeypatch.setattr(push, "find_center_silent", lambda *a, **k: None)

    result = flow._st_start_battle()
    assert result == push.STATE_DONE
    assert len(clicks) == 1


# ---------- 公会玩法：目录被误关后重开重试 ----------

def test_guild_play_reopens_catalog_when_closed(monkeypatch):
    open_calls = []
    scroll_calls = []
    find_seq = {
        flow_gonghui.tpl_tab_active: [(1, 1), (1, 1)],
        # 每轮卡片查找 3 次（首屏 + 逐次下滑 2 次）；第 2 轮首屏就命中
        "card.png": [None, None, None, (500, 500)],
        flow_gonghui.tpl_catalog_title: [None, None],
    }

    def fake_find(tpl, *args, **kwargs):
        seq = find_seq.get(tpl)
        return seq.pop(0) if seq else None

    monkeypatch.setattr(flow_gonghui, "open_wanfamulu",
                        lambda **k: open_calls.append(True) or True)
    monkeypatch.setattr(flow_gonghui, "find_center_silent", fake_find)
    monkeypatch.setattr(flow_gonghui, "scroll_in_client_region",
                        lambda *a, **k: scroll_calls.append(True) or True)
    monkeypatch.setattr(flow_gonghui, "click_position", lambda *a, **k: True)
    monkeypatch.setattr(flow_gonghui, "time", types.SimpleNamespace(sleep=lambda _s: None))
    monkeypatch.setattr(flow_gonghui, "check_stop", lambda: None)
    monkeypatch.setattr(flow_gonghui, "log", lambda *a, **k: None)

    assert flow_gonghui.flow_enter_guild_play("card.png", "结社战线") is True
    assert len(open_calls) == 2, "第一轮目录被误关后必须重开目录再试一轮"
    assert len(scroll_calls) == 2, "首屏没卡片的那一轮应逐次下滑 2 次"


# ---------- 公会日常：入口缺失记跳过（True） ----------

def test_guild_daily_skips_when_entry_missing(monkeypatch):
    monkeypatch.setattr(jieshezhanxian, "flow_enter_guild_play", lambda *a, **k: False)
    monkeypatch.setattr(jieshezhanxian, "flow_return_main", lambda: None)
    monkeypatch.setattr(jieshezhanxian, "check_and_handle_libao", lambda *a, **k: None)
    monkeypatch.setattr(jieshezhanxian, "log", lambda *a, **k: None)

    assert jieshezhanxian.main() is True


def test_hunt_daily_skips_when_entry_missing(monkeypatch):
    monkeypatch.setattr(lieshouxunshang, "_enter_panel", lambda: False)
    monkeypatch.setattr(lieshouxunshang, "check_and_handle_libao", lambda *a, **k: None)
    monkeypatch.setattr(lieshouxunshang, "flow_return_main", lambda: None)
    monkeypatch.setattr(lieshouxunshang, "log", lambda *a, **k: None)

    assert lieshouxunshang.main() is True


# ---------- 普竞：zhandou 被吞时补点，单场失败不中断剩余次数 ----------

def test_pujing_retries_zhandou_when_battle_button_stays(monkeypatch):
    import pujing

    events = []
    zhandou_hits = {"n": 0}

    def fake_wait_and_click(_tpl, name, *args, **kwargs):
        events.append(name)
        zhandou_hits["n"] += 1
        return zhandou_hits["n"] >= 2   # 第一次未出现、第二次成功

    monkeypatch.setattr(pujing, "send_coord", lambda *a, **k: events.append("send"))
    monkeypatch.setattr(pujing, "wait_and_click", fake_wait_and_click)
    monkeypatch.setattr(pujing, "find_center_silent", lambda *a, **k: (1, 1))
    monkeypatch.setattr(pujing, "random_sleep", lambda: None)
    monkeypatch.setattr(pujing, "time", types.SimpleNamespace(time=time.time,
                                                              sleep=lambda _s: None))
    monkeypatch.setattr(pujing, "wait_for_any",
                        lambda *a, **k: (pujing.tpl_tiaoguo, "tiaoguo", (5, 5)))
    monkeypatch.setattr(pujing, "wait_for_appearance", lambda *a, **k: (6, 6))

    assert pujing.execute_battle_flow(pujing.tpl_pujingzhandou, "pujingzhandou",
                                      (3, 3)) is True
    assert sum(1 for e in events if isinstance(e, str) and e.startswith("zhandou")) == 2


def test_pujing_continues_when_challenge_button_remains(monkeypatch):
    """单场失败但挑战按钮仍在：继续下一场，不许直接结束整轮（次数会残留）。"""
    import pujing

    outcomes = [False, True, True]
    fought = []
    challenge_seen = {"n": 0}

    def fake_battle(*args, **kwargs):
        fought.append(True)
        return outcomes.pop(0)

    def fake_wait_for_any(candidates, *args, **kwargs):
        names = [item[1] for item in candidates]
        if "kaishitiaozhan" in names or "pujingjixutiaozhan" in names:
            challenge_seen["n"] += 1
            if challenge_seen["n"] <= 3:
                return (pujing.tpl_kaishitiaozhan, "kaishitiaozhan", (2, 2))
            return None   # 第 4 轮挑战按钮消失 = 次数用尽，主循环正常收尾
        return None       # 门票检测：未出现提示 = 次数充足

    def fake_find(tpl, *args, **kwargs):
        # 弹窗清理循环里「连续 5 秒检测不到才算过」：该模板必须返回 None，
        # 否则每次命中都重置计时、循环永不结束（2026-11-08 自踩）。
        if tpl == pujing.tpl_dianjikongbaichuguanbi:
            return None
        return (1, 1)

    monkeypatch.setattr(pujing, "execute_battle_flow", fake_battle)
    monkeypatch.setattr(pujing, "find_center_silent", fake_find)
    monkeypatch.setattr(pujing, "open_wanfamulu", lambda *a, **k: True)
    monkeypatch.setattr(pujing, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(pujing, "wait_for_any", fake_wait_for_any)
    monkeypatch.setattr(pujing, "find_leftmost",
                        lambda *a, **k: (pujing.tpl_pujingzhandou, "pujingzhandou",
                                         (3, 3)))
    monkeypatch.setattr(pujing, "send_coord", lambda *a, **k: None)
    monkeypatch.setattr(pujing, "random_sleep", lambda: None)
    monkeypatch.setattr(pujing, "display_name", lambda name: name)
    monkeypatch.setattr(pujing, "time", types.SimpleNamespace(time=time.time,
                                                              sleep=lambda _s: None))

    assert pujing.flow_pujing() is True
    assert len(fought) == 3, "第 1 场失败后仍应继续打完剩余次数"


# ---------- 巅峰竞技场：失败页卡住时继续下一场 ----------

def test_dianfeng_continues_when_challenge_button_remains(monkeypatch):
    import dianfengjingjichang as df

    outcomes = [False, True, True]
    fought = []

    def fake_fight(index):
        fought.append(index)
        return outcomes.pop(0)

    monkeypatch.setattr(df, "_enter_dianfeng", lambda: True)
    monkeypatch.setattr(df, "_fight_once", fake_fight)
    monkeypatch.setattr(df, "find_center_silent", lambda *a, **k: (1, 1))
    monkeypatch.setattr(df, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(df, "recover_to_main_interface", lambda *a, **k: None)
    monkeypatch.setattr(df, "check_and_handle_libao", lambda *a, **k: None)
    monkeypatch.setattr(df, "log", lambda *a, **k: None)

    df.flow_dianfeng(challenge_count=3)
    assert fought == [1, 2, 3], "第 1 场失败后仍应打满 3 场（次数不残留）"


# ---------- 2026-11-09 实机失败修复 ----------

def test_guild_back_to_home_detects_saodang(monkeypatch):
    """扫荡按钮一开始就可见时，_back_to_guild_home 直接返回 True（不误退）。"""
    import jieshezhanxian as jsx

    monkeypatch.setattr(jsx, "find_center_silent", lambda *a, **k: (1, 1))
    assert jsx._back_to_guild_home() is True


def test_guild_challenge_does_not_exit_before_sweep(monkeypatch):
    """挑战结束不能再调用 _back_to_main（旧实现把结社页面关掉，导致扫荡找不到按钮）。

    2026-11-09 实机：挑战结束即退出 → 扫荡面板未打开 → 误判次数用尽。
    """
    import jieshezhanxian as jsx

    exited = []
    monkeypatch.setattr(jsx, "_click_and_expect", lambda *a, **k: True)
    monkeypatch.setattr(jsx, "_find", lambda *a, **k: (1, 1))
    monkeypatch.setattr(jsx, "_wait_any", lambda *a, **k: (jsx.tpl_defeat, (1, 1)))
    monkeypatch.setattr(jsx, "click_position", lambda *a, **k: True)
    monkeypatch.setattr(jsx, "check_stop", lambda: None)
    monkeypatch.setattr(jsx, "log", lambda *a, **k: None)
    monkeypatch.setattr(jsx, "_back_to_main", lambda *a, **k: exited.append(True))

    jsx._challenge_until_lose()
    assert exited == [], "挑战结束不应提前退出结社页面"


def test_dianfeng_offseason_returns_true(monkeypatch):
    """巅峰竞技场休赛期（入口拿不到挑战按钮）记跳过而不是任务失败。"""
    import dianfengjingjichang as df

    monkeypatch.setattr(df, "_enter_dianfeng", lambda: False)
    monkeypatch.setattr(df, "recover_to_main_interface", lambda *a, **k: None)
    monkeypatch.setattr(df, "log", lambda *a, **k: None)
    assert df.flow_dianfeng() is True


def test_loading_screen_detects_dark_frame(monkeypatch):
    """加载画面（近似全黑）要能识别，正常亮画面不能误判。"""
    import numpy as np

    import common

    monkeypatch.setattr(common, "game_client_region", lambda *a, **k: (0, 0, 1600, 900))
    monkeypatch.setattr(common, "screenshot_bgr",
                        lambda: np.zeros((1080, 3840, 3), dtype=np.uint8))
    assert common.is_loading_screen() is True

    monkeypatch.setattr(common, "screenshot_bgr",
                        lambda: np.full((1080, 3840, 3), 200, dtype=np.uint8))
    assert common.is_loading_screen() is False
