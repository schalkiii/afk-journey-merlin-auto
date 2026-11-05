"""红点领取模块：领取循环的计数、停止条件与上限保护。"""
import types

import numpy as np

import hongbaolingqu as hb


def test_claim_stops_when_nothing_left(monkeypatch):
    monkeypatch.setattr(hb, "wait_and_click", lambda *args, **kwargs: False)
    monkeypatch.setattr(hb, "find_center_silent", lambda *args, **kwargs: None)
    assert hb.claim_current_view() == 0


def test_claim_loop_uses_both_buttons_and_closes_popup(monkeypatch):
    """一键领取与单个领取混着出现时都要点到，且每次领取后都尝试关奖励弹窗。"""
    actions = []
    # 第 1 轮有一键领取，第 2 轮只剩单个领取，第 3 轮两者都没有
    yijian_results = iter([True, False, False])
    lingqu_results = iter([(1100, 400), None])

    def fake_wait_and_click(template_path, name, *args, **kwargs):
        if template_path == hb.tpl_yijianlingqu:
            return next(yijian_results)
        return False

    def fake_find(template_path, *args, **kwargs):
        if template_path == hb.tpl_blank_close:
            actions.append("close")
            return (100, 100)
        if template_path == hb.tpl_lingqu:
            return next(lingqu_results)
        return None

    monkeypatch.setattr(hb, "wait_and_click", fake_wait_and_click)
    monkeypatch.setattr(hb, "find_center_silent", fake_find)
    monkeypatch.setattr(hb, "click_blank_to_exit", lambda *args, **kwargs: actions.append("blank"))
    monkeypatch.setattr(hb, "click_position", lambda pos, **kwargs: actions.append(("click", pos)))

    assert hb.claim_current_view() == 2
    assert actions == [
        "close", "blank",
        ("click", (1100, 400)), "close", "blank",
    ]


def test_claim_loop_stops_at_cap(monkeypatch):
    """领取后界面不刷新时靠上限退出，不能死循环点同一个按钮。

    首轮走 wait_and_click，后续轮次走静默匹配；所以 fake 必须让静默匹配也
    持续命中，才能把循环推到上限（否则第二轮就因「没有可领项」正常退出）。
    """
    monkeypatch.setattr(hb, "wait_and_click", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        hb, "find_center_silent",
        lambda template_path, *args, **kwargs: (1100, 400)
        if template_path == hb.tpl_yijianlingqu else None,
    )
    monkeypatch.setattr(hb, "click_position", lambda pos, **kwargs: None)
    monkeypatch.setattr(hb, "click_blank_to_exit", lambda *args, **kwargs: None)
    assert hb.claim_current_view() == hb.MAX_CLAIM_PER_VIEW


def test_task_panel_falls_back_to_hud_target_entry(monkeypatch):
    """菜单→任务 进不去时改用主界面左下角「目标」直达入口，而不是直接放弃整个面板。"""
    tried = []
    monkeypatch.setattr(hb, "_open_task_panel_via_menu", lambda: False)
    monkeypatch.setattr(hb, "log", lambda *args, **kwargs: None)

    def fake_hud_entry():
        tried.append("hud")
        return True

    monkeypatch.setattr(hb, "_open_task_panel_via_hud", fake_hud_entry)

    assert hb._open_task_panel() is True
    assert tried == ["hud"]


def test_hud_target_entry_adds_client_origin(monkeypatch):
    """HUD 固定点位必须换算成整屏坐标——历史上多次因为直接把客户区坐标传进去而点空。"""
    clicks = []
    monkeypatch.setattr(hb, "check_stop", lambda: None)
    monkeypatch.setattr(hb, "game_client_region", lambda: (2000, 100, 1600, 900))
    monkeypatch.setattr(hb, "click_position", lambda pos, **kwargs: clicks.append(pos))
    monkeypatch.setattr(hb, "_panel_open", lambda: True)
    monkeypatch.setattr(hb, "time", types.SimpleNamespace(sleep=lambda *args: None))
    monkeypatch.setattr(hb, "log", lambda *args, **kwargs: None)

    assert hb._open_task_panel_via_hud() is True
    assert clicks[0] == (2000 + hb.TASK_PANEL_HUD_POS[0], 100 + hb.TASK_PANEL_HUD_POS[1])
    assert clicks[0] != hb.TASK_PANEL_HUD_POS


def test_hud_target_entry_retries_without_drifting_coordinate(monkeypatch):
    """confirm 恒为假：重试用尽返回 False，每轮连点两下，坐标始终是同一个「客户区原点 + 偏移」。

    twice=True 路径下每次 click_position 代表两下点击，所以有效点击次数 = retries×2。
    """
    clicks = []
    monkeypatch.setattr(hb, "check_stop", lambda: None)
    monkeypatch.setattr(hb, "game_client_region", lambda: (2000, 100, 1600, 900))
    monkeypatch.setattr(hb, "click_position",
                        lambda pos, **kwargs: clicks.append((pos, kwargs.get("twice"))))
    monkeypatch.setattr(hb, "_panel_open", lambda: False)
    monkeypatch.setattr(hb, "time", types.SimpleNamespace(sleep=lambda *args: None))
    monkeypatch.setattr(hb, "log", lambda *args, **kwargs: None)

    assert hb._open_task_panel_via_hud() is False

    expected = (2000 + hb.TASK_PANEL_HUD_POS[0], 100 + hb.TASK_PANEL_HUD_POS[1])
    assert len(clicks) == hb.ENTRY_RETRY
    assert all(pos == expected and twice is True for pos, twice in clicks), (
        "重试只能重复同一个入口点位，且每轮必须连点两下"
    )
    assert sum(2 if twice else 1 for _pos, twice in clicks) == hb.ENTRY_RETRY * 2


def _stub_journal(monkeypatch, switch_changed):
    """桩掉一记扫描的外部依赖；switch_changed 表示「子页签行是否确认发生了切换」。"""
    clicks = []
    swept = []
    monkeypatch.setattr(hb, "check_stop", lambda: None)
    monkeypatch.setattr(hb, "log", lambda *args, **kwargs: None)
    monkeypatch.setattr(hb, "game_client_region", lambda: (2000, 100, 1600, 900))
    monkeypatch.setattr(hb, "click_position", lambda pos, **kwargs: clicks.append(pos))
    monkeypatch.setattr(hb, "get_cached_screenshot",
                        lambda: np.zeros((900, 1600, 3), dtype=np.uint8))
    # 子页签行真切了会掉到 -0.3（实测），没切是 1.000；这里直接桩掉分数
    monkeypatch.setattr(hb.cv2, "matchTemplate",
                        lambda *args, **kwargs: np.array([[-0.3] if switch_changed else [1.0]]))

    def fake_sweep(view_name):
        swept.append(view_name)
        return 1

    monkeypatch.setattr(hb, "_sweep_view", fake_sweep)
    return clicks, swept


def test_journal_sweeps_three_task_sub_tabs_when_switch_confirmed(monkeypatch):
    """切页确认成功时，每日/每周/挑战三个子页签都要扫——漏掉就是整片周常奖励不领。"""
    clicks, swept = _stub_journal(monkeypatch, switch_changed=True)

    assert hb._sweep_journal("测试记") == 4
    assert sorted(s for s in swept if "任务子页" in s) == [
        "测试记-任务子页1", "测试记-任务子页2", "测试记-任务子页3"]
    # 扫完切回奖励页，让下一本记从已知状态开始
    assert clicks[-1] == (2000 + hb.JOURNAL_REWARD_TAB_POS[0], 100 + hb.JOURNAL_REWARD_TAB_POS[1])


def test_journal_stops_when_sub_tab_row_did_not_move(monkeypatch):
    """子页签行没动就说明没在任务页上，必须停：那三个坐标在奖励页落在奖励列表区。"""
    clicks, swept = _stub_journal(monkeypatch, switch_changed=False)

    assert hb._sweep_journal("测试记") == 1
    assert swept == ["测试记-奖励"]
    assert len(clicks) == 3, "只应点 切任务页 + 两个子页签试探，不能继续扫下去"


class _Clock:
    """可控时钟：_panel_open 同时用到 time.time 与 time.sleep。"""

    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _stub_panel_probe(monkeypatch, hit_round=None, hit_template=None):
    """桩掉页签检测；hit_round 轮（从 0 起）命中 hit_template，None 表示恒 miss。"""
    clock = _Clock()
    calls = []
    per_round = len(hb.PANEL_TAB_TEMPLATES)

    def fake_find(template_path, *args, **kwargs):
        round_index = len(calls) // per_round
        calls.append((template_path, kwargs.get("timeout")))
        if hit_round is not None and round_index == hit_round and template_path == hit_template:
            return (100, 100)
        return None

    monkeypatch.setattr(hb, "time", clock)
    monkeypatch.setattr(hb, "find_center_silent", fake_find)
    monkeypatch.setattr(hb, "check_stop", lambda: None)
    return clock, calls


def test_panel_open_returns_true_when_second_round_hits(monkeypatch):
    """第一轮全 miss、第二轮某页签命中 → True，且第二轮检查到命中即止。"""
    clock, calls = _stub_panel_probe(
        monkeypatch, hit_round=1, hit_template=hb.PANEL_TAB_TEMPLATES[2]
    )

    assert hb._panel_open() is True
    assert len(calls) == len(hb.PANEL_TAB_TEMPLATES) + 3
    assert [tpl for tpl, _timeout in calls[-3:]] == list(hb.PANEL_TAB_TEMPLATES[:3])
    assert all(timeout == 0 for _tpl, timeout in calls)
    assert clock.now == hb.PANEL_POLL_INTERVAL, "整轮无命中才等一个轮询间隔"


def test_panel_open_polls_single_frame_until_deadline(monkeypatch):
    """恒 miss：到 deadline 返回 False；每轮 4 个模板各查 1 次且都不带等待。"""
    clock, calls = _stub_panel_probe(monkeypatch, hit_round=None)

    assert hb._panel_open() is False
    per_round = len(hb.PANEL_TAB_TEMPLATES)
    assert len(calls) % per_round == 0
    rounds = len(calls) // per_round
    assert rounds >= int(hb.PANEL_OPEN_TIMEOUT / hb.PANEL_POLL_INTERVAL)
    for template in hb.PANEL_TAB_TEMPLATES:
        assert sum(1 for tpl, _timeout in calls if tpl == template) == rounds
    assert all(timeout == 0 for _tpl, timeout in calls)
    assert clock.now >= hb.PANEL_OPEN_TIMEOUT


def test_panel_open_short_circuits_on_first_hit(monkeypatch):
    """第一轮就命中时不再检查后面的模板，也不白等。"""
    clock, calls = _stub_panel_probe(
        monkeypatch, hit_round=0, hit_template=hb.PANEL_TAB_TEMPLATES[1]
    )

    assert hb._panel_open() is True
    assert calls == [(hb.PANEL_TAB_TEMPLATES[0], 0), (hb.PANEL_TAB_TEMPLATES[1], 0)]
    assert clock.now == 0.0


def test_claim_first_round_waits_for_yijian_then_zero(monkeypatch):
    """只有单个「领取」的界面：一键领取首轮 1s 宽限，后续改静默匹配；单个领取始终 0.5s。"""
    yijian_timeouts = []
    lingqu_timeouts = []
    lingqu_results = iter([(1100, 400), (1100, 400), (1100, 400), None])
    clicks = []

    def fake_wait_and_click(template_path, *args, **kwargs):
        if template_path == hb.tpl_yijianlingqu:
            yijian_timeouts.append(kwargs.get("timeout"))
        return False

    def fake_find(template_path, *args, **kwargs):
        if template_path == hb.tpl_lingqu:
            lingqu_timeouts.append(kwargs.get("timeout"))
            return next(lingqu_results)
        return None

    monkeypatch.setattr(hb, "wait_and_click", fake_wait_and_click)
    monkeypatch.setattr(hb, "find_center_silent", fake_find)
    monkeypatch.setattr(hb, "click_position", lambda pos, **kwargs: clicks.append(pos))

    assert hb.claim_current_view() == 3
    assert clicks == [(1100, 400)] * 3
    assert yijian_timeouts == [hb.YIJIAN_FIRST_TIMEOUT], (
        "首轮之后不再调用 wait_and_click（避免每轮打印「放弃 yijianlingqu」）"
    )
    assert lingqu_timeouts == [0.5, 0.5, 0.5, 0.5]


def test_claim_later_rounds_use_silent_find_for_yijian(monkeypatch):
    """首轮一键领取走 wait_and_click(1s)；后续轮次改静默匹配 + click_position，不再打「放弃」。"""
    wait_timeouts = []
    yijian_find_timeouts = []
    lingqu_results = iter([(1100, 400), (1100, 400), (1100, 400), None])
    clicks = []

    def fake_wait_and_click(template_path, *args, **kwargs):
        if template_path == hb.tpl_yijianlingqu:
            wait_timeouts.append(kwargs.get("timeout"))
        return False

    def fake_find(template_path, *args, **kwargs):
        if template_path == hb.tpl_yijianlingqu:
            yijian_find_timeouts.append(kwargs.get("timeout"))
            return None
        if template_path == hb.tpl_lingqu:
            return next(lingqu_results)
        return None

    monkeypatch.setattr(hb, "wait_and_click", fake_wait_and_click)
    monkeypatch.setattr(hb, "find_center_silent", fake_find)
    monkeypatch.setattr(hb, "click_position", lambda pos, **kwargs: clicks.append(pos))

    assert hb.claim_current_view() == 3
    assert wait_timeouts == [hb.YIJIAN_FIRST_TIMEOUT], "后续轮次不得再调用 wait_and_click"
    assert yijian_find_timeouts == [0, 0, 0]
    assert clicks == [(1100, 400)] * 3


def _stub_task_panel(monkeypatch):
    """桩掉任务面板扫描的外部依赖，记录实际扫过的页签名。"""
    swept = []
    monkeypatch.setattr(hb, "check_stop", lambda: None)
    monkeypatch.setattr(hb, "log", lambda *args, **kwargs: None)
    monkeypatch.setattr(hb, "time", types.SimpleNamespace(sleep=lambda *args: None))
    monkeypatch.setattr(hb, "wait_and_click", lambda *args, **kwargs: True)
    monkeypatch.setattr(hb, "game_client_region", lambda: (2000, 100, 1600, 900))
    monkeypatch.setattr(hb, "click_position", lambda *args, **kwargs: None)
    monkeypatch.setattr(hb, "_sweep_view", lambda name: swept.append(name) or 1)
    monkeypatch.setattr(hb, "_sweep_season_task_tab",
                        lambda: swept.append("赛季任务-二级") or 1)
    return swept


def test_task_panel_skips_daily_when_disabled(monkeypatch):
    swept = _stub_task_panel(monkeypatch)
    hb._claim_task_panel({"claim_daily": False})
    assert "每日任务" not in swept
    assert "公会任务" in swept


def test_task_panel_skips_guild_when_disabled(monkeypatch):
    swept = _stub_task_panel(monkeypatch)
    hb._claim_task_panel({"claim_guild": False})
    assert "公会任务" not in swept
    assert "每日任务" in swept


def test_task_panel_skips_growth_when_disabled(monkeypatch):
    swept = _stub_task_panel(monkeypatch)
    hb._claim_task_panel({"claim_growth": False})
    assert "成长挑战" not in swept
    assert "家园目标" in swept


def test_task_panel_skips_season_when_disabled(monkeypatch):
    swept = _stub_task_panel(monkeypatch)
    hb._claim_task_panel({"claim_season": False})
    assert "赛季任务-二级" not in swept
    assert "成长挑战" in swept


def test_task_panel_skips_homestead_when_disabled(monkeypatch):
    swept = _stub_task_panel(monkeypatch)
    hb._claim_task_panel({"claim_homestead": False})
    assert "家园目标" not in swept
    assert "成长挑战" in swept


def _stub_main(monkeypatch):
    """桩掉 main 的全部入口，记录实际执行过的子项。"""
    calls = []
    monkeypatch.setattr(hb, "check_stop", lambda: None)
    monkeypatch.setattr(hb, "log", lambda *args, **kwargs: None)
    monkeypatch.setattr(hb, "time", types.SimpleNamespace(sleep=lambda *args: None))
    monkeypatch.setattr(hb, "recover_to_main_interface", lambda: True)
    monkeypatch.setattr(hb, "find_center_silent", lambda *args, **kwargs: (100, 100))
    monkeypatch.setattr(hb, "_open_task_panel", lambda: True)
    monkeypatch.setattr(hb, "_click_panel_back", lambda name: True)
    monkeypatch.setattr(hb, "_claim_task_panel",
                        lambda params=None: calls.append("task_panel") or 1)
    monkeypatch.setattr(hb, "_claim_season_book",
                        lambda pos: calls.append("season_book") or 1)
    monkeypatch.setattr(hb, "_sweep_laurel_journey",
                        lambda: calls.append("laurel") or 1)
    monkeypatch.setattr(hb, "_sweep_progress_milestones",
                        lambda: calls.append("idle") or 1)
    return calls


def test_main_skips_season_book_when_disabled(monkeypatch):
    calls = _stub_main(monkeypatch)
    assert hb.main({"claim_season_book": False}) is True
    assert calls == ["task_panel", "laurel", "idle"]


def test_main_skips_laurel_and_idle_when_disabled(monkeypatch):
    calls = _stub_main(monkeypatch)
    assert hb.main({"claim_laurel": False, "claim_idle": False}) is True
    assert calls == ["task_panel", "season_book"]


def test_main_skips_task_panel_when_all_its_switches_off(monkeypatch):
    calls = _stub_main(monkeypatch)
    opened = []
    monkeypatch.setattr(hb, "_open_task_panel", lambda: opened.append(True) or True)

    params = {key: False for key in hb.TASK_PANEL_KEYS}
    assert hb.main(params) is True
    assert opened == [], "任务面板相关开关全关时不应再去打开面板"
    assert calls == ["season_book", "laurel", "idle"]


def test_main_all_switches_off_returns_true_and_logs_once(monkeypatch):
    calls = _stub_main(monkeypatch)
    logs = []
    monkeypatch.setattr(hb, "log", lambda msg: logs.append(msg))

    params = {key: False for key in hb.CLAIM_SUB_KEYS}
    assert hb.main(params) is True
    assert calls == []
    assert logs.count("红点领取子项全部关闭，本次跳过") == 1


def _stub_season_task_tab(monkeypatch, anchor):
    """桩掉赛季任务页扫描，返回实际点击的整屏坐标与扫过的视图名。"""
    clicks = []
    swept = []
    monkeypatch.setattr(hb, "check_stop", lambda: None)
    monkeypatch.setattr(hb, "log", lambda *args, **kwargs: None)
    monkeypatch.setattr(hb, "game_client_region", lambda: (2000, 100, 1600, 900))
    monkeypatch.setattr(hb, "click_position", lambda pos, **kwargs: clicks.append(pos))
    monkeypatch.setattr(hb, "wait_and_click", lambda *args, **kwargs: False)
    monkeypatch.setattr(hb, "find_center_silent", lambda *args, **kwargs: anchor)
    monkeypatch.setattr(hb, "_sweep_view", lambda name: swept.append(name) or 0)
    return clicks, swept


def test_season_tab_falls_back_to_fixed_points_when_anchor_missing(monkeypatch):
    """「玩法」锚点识别不到时必须按固定点位把 5 个页签都扫一遍，而不是整段跳过。

    锚点与「赛季阶段」页签模板都识别不到时，先按固定点切到「赛季阶段」子页，
    再按固定栅格扫 5 个分类页签。
    """
    clicks, swept = _stub_season_task_tab(monkeypatch, None)

    hb._sweep_season_task_tab()

    stage_pos = (2000 + hb.SEASON_STAGE_SUB_TAB_POS[0], 100 + hb.SEASON_STAGE_SUB_TAB_POS[1])
    base_x, base_y = hb.SEASON_SUB_TAB_FALLBACK_ORIGIN
    expected = [stage_pos] + [(2000 + base_x + offset, 100 + base_y)
                              for offset in hb.SEASON_SUB_TAB_OFFSET_X]
    assert clicks == expected
    assert [name for name in swept if name.startswith("赛季任务-固定页")] == [
        f"赛季任务-固定页(偏移 {offset})" for offset in hb.SEASON_SUB_TAB_OFFSET_X]


def test_season_tab_keeps_anchor_offsets_when_found(monkeypatch):
    """锚点命中时仍以锚点为基准做横向偏移，保持原逻辑不变。"""
    clicks, swept = _stub_season_task_tab(monkeypatch, (960, 300))

    hb._sweep_season_task_tab()

    assert clicks == [(960 + offset, 300) for offset in hb.SEASON_SUB_TAB_OFFSET_X]
    assert [name for name in swept if name.startswith("赛季任务-二级页")] == [
        f"赛季任务-二级页(偏移 {offset})" for offset in hb.SEASON_SUB_TAB_OFFSET_X]
    assert not any(name.startswith("赛季任务-固定页") for name in swept)
