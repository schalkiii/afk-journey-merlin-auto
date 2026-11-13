"""2026-11-13 实跑暴露的四处「判据成立但现实没动」回归测试。

对应现场：
- 女神塔 09:02:46 点完卡片仍停在玩法目录，脚本却认定已进入，靠用户手动点进去；
- 巅峰竞技场 09:08:19→09:11:25 一次性长等 180 秒，随后「完成 0 场」仍打 ✔；
- 迷梦之域 09:02:19 玩家信息卡片遮挡，返回按钮 3 轮 × 1.5s 找不到后判失败；
- 推图 09:26:38/41 买完门票的过渡态被误判成遮挡面板，连点两次返回退回玩法目录。

负验证（改回坏实现时必须失败）：
1. 首次进入改回 `wait_and_click` → `test_nvshenta_entry_confirms_page_switch` 失败；
2. `_fight_once` 改回 `_wait_for_any(timeout=180)` → `test_fight_once_uses_short_poll` 失败；
3. `flow_dianfeng` 末尾改回 `return True` → `test_zero_battles_is_failure` 失败；
4. 排行榜礼包去掉主界面确认 → `test_rank_gift_needs_main_interface` 失败；
5. `_st_limit` 去掉 `allow_occluder=False` → `test_ticket_wait_disables_occluder` 失败。
"""

import common
import dianfengjingjichang as df
import Goldenhandmaidens as gh
import mimengzhiyu as mimeng
import nvshenta
import push

# ---------- 1. 女神塔：跳转型入口必须确认界面真的切换 ----------

def test_nvshenta_entry_confirms_page_switch(monkeypatch):
    """点塔卡片后若仍停在玩法目录，必须补点/放弃，不能当成已进入继续往下走。"""
    calls = []
    monkeypatch.setattr(nvshenta, "open_wanfamulu", lambda **_k: True)
    monkeypatch.setattr(nvshenta, "random_sleep", lambda: None)
    monkeypatch.setattr(nvshenta, "click_and_confirm",
                        lambda tpl, name, confirm, **kw: calls.append(
                            (tpl, name, confirm, kw)) or False)
    monkeypatch.setattr(nvshenta, "wait_and_click",
                        lambda *a, **_k: (_ for _ in ()).throw(
                            AssertionError("首次进入不该再用裸 wait_and_click")))

    assert nvshenta.flow_nvshenta() is False
    assert len(calls) == 1, "首次进入必须走 click_and_confirm"
    assert calls[0][0] == nvshenta.tpl_nvshenta
    assert calls[0][2] is nvshenta._tower_page_open
    assert calls[0][3]["confirm_timeout"] >= 10.0


# ---------- 2. 巅峰竞技场：点战斗之后同样不能盲等 180 秒 ----------

def test_fight_once_uses_short_poll():
    """`_fight_once` 等第一个信号必须走短轮询封装，而不是 `_wait_for_any(180)`。

    这里用源码契约而不是驱动真实 `_fight_once`：后者会在用例里点「继续挑战」、
    调用 `open_wanfamulu` 并截屏（游戏开着必失败、关着白等），属测试自身不确定。
    短轮询的行为由 `test_battle_outcome_reclicks_zhandou` 单独覆盖。
    """
    import inspect

    source = inspect.getsource(df._fight_once)
    assert "_wait_for_battle_outcome()" in source
    assert "timeout=MAX_BATTLE_TIME" not in source


def test_battle_outcome_reclicks_zhandou(monkeypatch):
    """点完战斗仍停在阵容页（战斗按钮可见）时补点，而不是把 180 秒耗光。"""
    clicks = []
    polls = []
    state = {"n": 0}
    monkeypatch.setattr(df, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(df, "check_stop", lambda: None)
    monkeypatch.setattr(df, "click_position", lambda pos, **_k: clicks.append(pos))
    monkeypatch.setattr(df, "_wait_for_any", lambda *_a, **_k: polls.append(1))
    monkeypatch.setattr(df, "is_loading_screen", lambda: False)
    monkeypatch.setattr(df, "capture_failure_context", lambda *_a, **_k: None)

    def fake_find(tpl, *_a, **_k):
        if tpl == df.tpl_zhandou:
            state["n"] += 1
            return (1139, 897) if state["n"] <= 2 else None
        return None

    monkeypatch.setattr(df, "find_center_silent", fake_find)

    assert df._wait_for_battle_outcome() is None
    assert clicks == [(1139, 897), (1139, 897)], "战斗按钮还在就必须补点"
    assert len(polls) == df.OUTCOME_STALL_LIMIT + 2


def test_zero_battles_is_failure(monkeypatch):
    """完成 0 场不能打 ✔（2026-11-13 日志里「✔ 245.8s」的假成功）。"""
    monkeypatch.setattr(df, "recover_to_main_interface", lambda: None)
    monkeypatch.setattr(df, "_enter_dianfeng", lambda: True)
    monkeypatch.setattr(df, "_fight_once", lambda _i: False)
    monkeypatch.setattr(df, "_back_to_challenge_view", lambda: False)
    monkeypatch.setattr(df, "find_center_silent", lambda *_a, **_k: None)
    monkeypatch.setattr(df, "wait_and_click", lambda *_a, **_k: True)
    monkeypatch.setattr(df, "check_and_handle_libao", lambda: None)
    monkeypatch.setattr(df, "log", lambda *_a, **_k: None)

    assert df.flow_dianfeng(1) is False


# ---------- 3. 迷梦之域：固定点位前先确认页面、弹窗优先清理 ----------

def test_rank_gift_needs_main_interface(monkeypatch):
    """没确认进入迷梦主界面就点固定坐标，会误开玩家信息卡片并遮挡整项任务。"""
    clicked = []
    monkeypatch.setattr(mimeng, "game_client_region", lambda: (0, 0, 1600, 900))
    monkeypatch.setattr(mimeng, "find_center_silent", lambda *_a, **_k: None)
    monkeypatch.setattr(mimeng, "click_position",
                        lambda pos, **_k: clicked.append(pos))
    monkeypatch.setattr(mimeng, "log", lambda *_a, **_k: None)

    assert mimeng._claim_rank_gift() is False
    assert clicked == [], "界面未确认时不得点固定坐标"


def test_mimeng_return_dismisses_popup_first(monkeypatch):
    """弹窗遮挡时优先关弹窗；旧实现每轮先耗 1.5 秒等根本不可见的返回按钮。"""
    dismissed = []
    exitck_calls = []
    state = {"n": 0}
    monkeypatch.setattr(mimeng.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(mimeng, "dismiss_popup_away_from",
                        lambda: dismissed.append(1) or True)
    monkeypatch.setattr(mimeng, "wait_and_click",
                        lambda *_a, **_k: exitck_calls.append(1) or True)

    def fake_find(tpl, *_a, **_k):
        if tpl == mimeng.tpl_tiaozhan:
            state["n"] += 1
            return (100, 100) if state["n"] >= 3 else None
        if tpl == mimeng.tpl_dianjikongbaichuguanbi:
            return (1120, 902)
        return None

    monkeypatch.setattr(mimeng, "find_center_silent", fake_find)

    assert mimeng._ensure_mimeng_main() is True
    assert len(dismissed) == 2
    assert exitck_calls == [], "弹窗还开着时不该去等返回按钮"


# ---------- 4. 推图：门票过渡态禁止「清遮挡」、一次动作最多清一次 ----------

def test_ticket_wait_disables_occluder(monkeypatch):
    """买完门票后只等 autocha，绝不能点 exit（现场：连点两次退回玩法目录）。"""
    flow = push.PushFlow()
    kwargs_seen = []
    monkeypatch.setattr(push, "find_center_silent", lambda *_a, **_k: (1, 1))
    monkeypatch.setattr(push, "wait_and_click", lambda *_a, **_k: True)
    monkeypatch.setattr(flow, "_wait_after_action",
                        lambda *_a, **_k: kwargs_seen.append(_k) or push.tpl_autocha)
    monkeypatch.setattr(flow, "_done", lambda ok: ("done", ok))

    assert flow._st_limit() == push.STATE_START_BATTLE
    assert kwargs_seen[0]["allow_occluder"] is False
    assert kwargs_seen[0]["timeout"] >= 15.0


def test_occluder_cleared_at_most_once(monkeypatch):
    """一次等待里最多清一次遮挡，防止连点返回把界面退飞。

    用「第 12 次探测才命中目标」驱动固定轮数，不依赖真实时钟：早先用 20ms 时间窗
    凑轮数，全量负载下连 3 轮都没跑到就退出，用例自身变成了 flaky。
    """
    flow = push.PushFlow()
    clears = []
    state = {"rounds": 0}

    def fake_find(tpl, *_a, **_k):
        if tpl == push.tpl_autocha:
            state["rounds"] += 1
            return (1, 1) if state["rounds"] >= 12 else None
        return None

    monkeypatch.setattr(push, "find_center_silent", fake_find)
    monkeypatch.setattr(flow, "_clear_occluder", lambda: clears.append(1) or True)

    assert flow._wait_for_any_state(
        [(push.tpl_autocha, 0.8)], timeout=30.0, interval=0
    ) == push.tpl_autocha
    assert len(clears) == 1, f"只允许清一次，实际 {len(clears)} 次"


# ---------- 5. 构建标识与会话结论强度 ----------

class _LogHost:
    def __init__(self):
        self.logs = []

    def log(self, msg):
        self.logs.append(msg)


def test_build_banner_reports_exe_timestamp(monkeypatch):
    """打包版必须把 exe 与打包时间写进日志，否则分不清跑的是哪一份成品。"""
    monkeypatch.setattr(gh.sys, "frozen", True, raising=False)
    monkeypatch.setattr(gh.sys, "executable", r"C:\bot\goldenhandmaidens.exe",
                        raising=False)
    monkeypatch.setattr(gh.os.path, "getmtime", lambda _p: 1763000000)
    host = _LogHost()
    gh.GameBotGUI._log_build_banner(host)
    assert any("打包于" in m and "goldenhandmaidens.exe" in m for m in host.logs)


def test_build_banner_marks_source_run(monkeypatch):
    monkeypatch.delattr(gh.sys, "frozen", raising=False)
    host = _LogHost()
    gh.GameBotGUI._log_build_banner(host)
    assert any("Python 源码" in m for m in host.logs)


def test_session_note_is_not_absolute(monkeypatch):
    """11-13 实测跨会话仍可点击生效，会话不一致只能作线索、不能断言必然失效。"""
    monkeypatch.setattr(common, "game_window_session_id", lambda: 1)
    monkeypatch.setattr(common, "_clicker_session_ids", lambda: [3])
    note = common.clicker_session_mismatch()
    assert note is not None
    assert "不会有任何反应" not in note
    assert "提权" in note
