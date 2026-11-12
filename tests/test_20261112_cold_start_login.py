"""2026-11-12 冷启动链路：等游戏就绪 + 登录流程如实反馈结果。

负验证留痕（把对应修复改回去，下列用例必须失败）：
- `common.wait_for_game_ready` 去掉「客户区尺寸」判断 →
  `test_ready_blocks_when_client_size_wrong` 必须失败（会误判 ok）；
- 把「命中游戏内界面标志」改回「画面不黑即就绪」→
  `test_ready_requires_in_game_marker` 必须失败（实测资源校验画面中心够亮，会被误判 ok）；
- `start.main` 恢复成恒返回 True（或直接 return None）→
  `test_login_reports_failure_when_not_at_main` 必须失败；
- `start._dismiss_popups` 去掉通用「点击空白处关闭」分支 →
  `test_login_dismisses_generic_popup` 必须失败。
"""
import common
import start

# ---------- wait_for_game_ready ----------

def _patch_probe(monkeypatch, markers, regions=None):
    """按调用序号驱动探针：markers 依次是每轮命中的界面标志（None=没有标志）。"""
    seq = list(markers)
    region_seq = list(regions) if regions else None
    state = {"marker": 0, "region": 0}

    def fake_region():
        if region_seq:
            idx = min(state["region"], len(region_seq) - 1)
            state["region"] += 1
            return region_seq[idx]
        return (1778, 75, common.CLIENT_WIDTH, common.CLIENT_HEIGHT)

    def fake_marker():
        idx = min(state["marker"], len(seq) - 1)
        state["marker"] += 1
        return seq[idx]

    monkeypatch.setattr(common, "find_game_window", lambda: 1001)
    monkeypatch.setattr(common, "game_client_region", fake_region)
    monkeypatch.setattr(common, "_game_ready_marker", fake_marker)
    monkeypatch.setattr(common, "check_stop", lambda: None)
    monkeypatch.setattr(common, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)
    return state


def test_ready_requires_in_game_marker(monkeypatch):
    """资源校验画面中心很亮（实测「正在更新游戏资源 21%」），不黑≠可操作。"""
    _patch_probe(monkeypatch, [None])
    status, msg = common.wait_for_game_ready(timeout=2.0)
    assert status == "not_ready", msg
    assert "标志" in msg, msg


def test_ready_ok_when_marker_appears(monkeypatch):
    """开始界面出现即视为可操作（登录任务会去点「点击开始游戏」）。"""
    _patch_probe(monkeypatch, [None, None, "开始界面"])
    status, msg = common.wait_for_game_ready(timeout=5.0)
    assert status == "ok", msg
    assert "开始界面" in msg


def test_ready_markers_cover_start_and_main():
    """标志必须同时覆盖「开始界面」与「主界面」两种合法落点。"""
    names = {name for _label, name in common.GAME_READY_MARKERS}
    assert "start.png" in names
    assert "wanfamulu.png" in names


def test_ready_blocks_when_client_size_wrong(monkeypatch):
    """客户区尺寸与模板基准不符时绝不能判就绪：模板会整体错位，所有点击都偏。"""
    _patch_probe(monkeypatch, ["主界面"] * 10, regions=[(1778, 75, 1280, 720)])
    status, msg = common.wait_for_game_ready(timeout=2.0)
    assert status == "not_ready", msg
    assert "尺寸" in msg, msg


def test_ready_ok_after_size_settles(monkeypatch):
    """窗口在启动动画里先小后正常：尺寸稳定且出现标志后应当放行。"""
    _patch_probe(
        monkeypatch,
        ["主界面"] * 10,
        regions=[(1778, 75, 1280, 720), (1778, 75, 1600, 900)],
    )
    status, msg = common.wait_for_game_ready(timeout=5.0)
    assert status == "ok", msg


def test_ready_reports_no_window(monkeypatch):
    monkeypatch.setattr(common, "find_game_window", lambda: None)
    monkeypatch.setattr(common, "check_stop", lambda: None)
    monkeypatch.setattr(common, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)
    status, msg = common.wait_for_game_ready(timeout=1.0)
    assert status == "no_window"
    assert "未找到游戏窗口" in msg


# ---------- 登录流程必须如实返回 ----------

def test_login_reports_failure_when_not_at_main(monkeypatch):
    """弹窗清完却始终没到主界面：必须返回 False，不能像旧实现那样恒报成功。"""
    monkeypatch.setattr(start, "wait_for_game_ready", lambda **_k: ("ok", "就绪"))
    monkeypatch.setattr(start, "_wait_for_start", lambda *_a, **_k: True)
    monkeypatch.setattr(start, "_dismiss_popups", lambda *_a, **_k: None)
    monkeypatch.setattr(start, "at_main_interface", lambda: False)
    monkeypatch.setattr(start, "_find", lambda *_a, **_k: None)
    monkeypatch.setattr(start, "LOGIN_READY_TIMEOUT", 0.05)
    monkeypatch.setattr(start.time, "sleep", lambda _s: None)

    assert start.main() is False


def test_login_reports_success_at_main(monkeypatch):
    monkeypatch.setattr(start, "wait_for_game_ready", lambda **_k: ("ok", "就绪"))
    monkeypatch.setattr(start, "_wait_for_start", lambda *_a, **_k: True)
    monkeypatch.setattr(start, "_dismiss_popups", lambda *_a, **_k: None)
    monkeypatch.setattr(start, "at_main_interface", lambda: True)

    assert start.main() is True


def test_login_aborts_without_window(monkeypatch):
    monkeypatch.setattr(start, "wait_for_game_ready", lambda **_k: ("no_window", "没窗口"))
    assert start.main() is False


def test_login_dismisses_generic_popup(monkeypatch):
    """冷启动叠着的公告/活动弹窗只带「点击空白处关闭」，必须也被清掉。"""
    clicked = []
    state = {"hint": 0}
    clock = {"t": 0.0}

    def fake_find(template_path, *_a, **_k):
        # 月卡/礼包都不可见，只有通用「点击空白处关闭」提示连着出现两次
        if "dianjikongbaichuguanbi" in str(template_path):
            state["hint"] += 1
            return (1129, 902) if state["hint"] <= 2 else None
        return None

    def fake_time():
        clock["t"] += 1.0
        return clock["t"]

    monkeypatch.setattr(start, "_find", fake_find)
    monkeypatch.setattr(start, "wait_and_click",
                        lambda path, name, *_a, **_k: clicked.append(name) or True)
    monkeypatch.setattr(start.time, "sleep", lambda _s: None)
    monkeypatch.setattr(start, "POPUP_IDLE_TIMEOUT", 0.0)
    monkeypatch.setattr(start.time, "time", fake_time)

    start._dismiss_popups("a", "b", "c")
    assert clicked, "通用「点击空白处关闭」弹窗必须被处理，否则主界面一直被挡"


# ---------- 会话一致性：注入器必须和游戏在同一个 Windows 会话 ----------
# 负验证：把 `clicker_session_mismatch` 改成恒返回 None（即恢复「只判进程存在」），
# `test_clicker_session_mismatch_detected` 必须失败。

def test_clicker_session_mismatch_detected(monkeypatch):
    """注入器在 RDP 会话、游戏在 Console：必须报出来。"""
    monkeypatch.setattr(common, "game_window_session_id", lambda: 1)
    monkeypatch.setattr(common, "_clicker_session_ids", lambda: [3])
    note = common.clicker_session_mismatch()
    assert note is not None
    assert "会话 3" in note and "会话 1" in note


def test_clicker_session_match_is_ok(monkeypatch):
    monkeypatch.setattr(common, "game_window_session_id", lambda: 1)
    monkeypatch.setattr(common, "_clicker_session_ids", lambda: [1])
    assert common.clicker_session_mismatch() is None


def test_clicker_session_unknown_is_ok(monkeypatch):
    """取不到会话号时不能误报——宁可放过也不能把正常环境判成故障。"""
    monkeypatch.setattr(common, "game_window_session_id", lambda: None)
    monkeypatch.setattr(common, "_clicker_session_ids", lambda: [3])
    assert common.clicker_session_mismatch() is None

    monkeypatch.setattr(common, "game_window_session_id", lambda: 1)
    monkeypatch.setattr(common, "_clicker_session_ids", list)
    assert common.clicker_session_mismatch() is None


def test_session_warning_logged_only_once(monkeypatch):
    lines = []
    monkeypatch.setitem(common._session_warn, "checked", False)
    monkeypatch.setitem(common._session_warn, "done", False)
    monkeypatch.setattr(common, "game_window_session_id", lambda: 1)
    monkeypatch.setattr(common, "_clicker_session_ids", lambda: [3])
    monkeypatch.setattr(common, "log", lambda msg, *_a, **_k: lines.append(msg))

    common.log_clicker_session_warning()
    common.log_clicker_session_warning()
    assert len(lines) == 1, "同一条告警不应每次点击都刷一遍"


# ---------- 定时触发：改时间不能留下两条循环 ----------
# 负验证：去掉 `_schedule_gen` 判断（`_schedule_loop` 忽略入参）→
# `test_schedule_loop_exits_when_superseded` 必须失败；
# 去掉 `_last_fire_ts` 护栏 → `test_fire_schedule_ignores_duplicate` 必须失败。

def test_schedule_loop_exits_when_superseded():
    """旧代号（被新设定取代）的循环必须立刻退出，否则到点会触发两次。"""
    import Goldenhandmaidens as gh

    class Fake:
        _schedule_gen = 5
        schedule_active = True
        scheduled_time = None
        schedule_cancel_event = None
        is_running = False

    # 代号 4 != 当前 5 → 直接返回，不会碰 scheduled_time/cancel_event（都是 None，
    # 一旦继续往下走就会 AttributeError，所以「能正常返回」本身就是断言）
    assert gh.GameBotGUI._schedule_loop(Fake(), 4) is None

    # 代号相同则继续走常规判断；schedule_active=False 时同样应干净返回
    class Done(Fake):
        schedule_active = False

    assert gh.GameBotGUI._schedule_loop(Done(), 5) is None


def test_fire_schedule_ignores_duplicate(monkeypatch):
    """同一时刻被两条循环触发时，只允许真正开跑一次。"""
    import Goldenhandmaidens as gh

    monkeypatch.setattr(gh, "is_game_running", lambda: True)

    class Fake:
        _last_fire_ts = 0.0
        schedule_active = True
        scheduled_time = object()

        is_running = False

        def __init__(self):
            self.launches = []
            self.logs = []

        def log(self, msg):
            self.logs.append(msg)

        def launch_game_then_start(self, launch_game=True):
            self.launches.append(launch_game)

        def set_schedule(self):
            pass

        def _set_schedule_status(self, _text):
            pass

    fake = Fake()
    gh.GameBotGUI._fire_schedule(fake)
    gh.GameBotGUI._fire_schedule(fake)

    assert fake.launches == [False], "重复触发必须被挡掉，否则游戏会被拉起两次"
    assert any("忽略本次重复触发" in m for m in fake.logs)


# ---------- 冷启动必须有人把游戏送进主界面 ----------
# 负验证：把 `_should_login_before_flow` 改成恒返回 False（即恢复「冷启动不补登录」）→
# `test_cold_launch_runs_login_first` 必须失败。

class _Script:
    def __init__(self, name, enabled):
        self.name = name
        self.enabled = enabled


def _after_ready_stub(monkeypatch, *, cold, scripts):
    """构造一个只够 `_after_game_ready` 用的 GUI 替身。"""
    import Goldenhandmaidens as gh

    monkeypatch.setattr(gh, "focus_game_window", lambda: (True, "已将游戏窗口切换到前台"))

    class Stub:
        # 复用真实判定：把未绑定函数塞进类属性即变成方法，避免把被测逻辑自己也打桩掉
        _should_login_before_flow = gh.GameBotGUI._should_login_before_flow

        def __init__(self):
            self._cold_launch = cold
            self.scripts = [_Script(n, e) for n, e in scripts]
            self.calls = []

        def log(self, _msg):
            pass

        def start_all(self):
            self.calls.append("start_all")

        def _run_login_before_flow(self):
            self.calls.append("login")

    stub = Stub()
    gh.GameBotGUI._after_game_ready(stub, "ok", "游戏已就绪")
    return stub


def test_cold_launch_runs_login_first(monkeypatch):
    """冷启动且「登录」不在任务列表里：必须先补登录，不能直接开跑任务。"""
    stub = _after_ready_stub(monkeypatch, cold=True,
                             scripts=[("邮件", True), ("好友奖励", True)])
    assert stub.calls == ["login"], f"冷启动应先走登录，实际 {stub.calls}"


def test_cold_launch_defers_to_login_task(monkeypatch):
    """「登录」已在列表里（第一项）时不要重跑一次。"""
    stub = _after_ready_stub(monkeypatch, cold=True,
                             scripts=[("登录", True), ("邮件", True)])
    assert stub.calls == ["start_all"]


def test_warm_launch_skips_login(monkeypatch):
    """游戏本来就在跑（热重启）：界面没变，多点一次开始反而有风险。"""
    stub = _after_ready_stub(monkeypatch, cold=False,
                             scripts=[("邮件", True)])
    assert stub.calls == ["start_all"]


# ---------- 任务闸：自带入口保障的任务不该被「先回主界面」拦下 ----------
# 负验证：把 `SELF_ENTRY_TASKS` 收回只含「登录」→
# `test_self_entry_task_bypasses_main_gate` 必须失败。

class _RootStub:
    def after(self, *_args):
        pass


def _gate_stub(monkeypatch, ensure_result):
    """只够 `_skip_task_when_not_at_main` 用的 GUI 替身，并记录是否尝试过通用回退。"""
    import Goldenhandmaidens as gh

    calls = []
    monkeypatch.setattr(gh.common, "ensure_main_interface",
                        lambda: calls.append(1) or ensure_result)
    monkeypatch.setattr(gh.common, "capture_failure_context", lambda *_a, **_k: None)

    class Stub:
        _skip_task_when_not_at_main = gh.GameBotGUI._skip_task_when_not_at_main

        def __init__(self):
            self.root = _RootStub()
            self.logs = []

        def log(self, msg):
            self.logs.append(msg)

        def update_script_panel(self):
            pass

    return Stub(), calls


def test_self_entry_task_bypasses_main_gate(monkeypatch):
    """家园愿望单面板开着时，通用回退点 6 轮都退不出来（← 只到家园视图，那里没有退出模板）。

    它自己的 `_ensure_panel` 能直接接管（`xinyuandanbiaoti` 实测 0.999），
    所以不该先去撞那 30 秒。
    """
    import Goldenhandmaidens as gh

    stub, calls = _gate_stub(monkeypatch, ensure_result=False)
    skipped = gh.GameBotGUI._skip_task_when_not_at_main(
        stub, _Script("家园愿望单", True), 1, 1, 0.0)
    assert skipped is False
    assert calls == [], "自带入口的任务不该去尝试通用回退"


def test_other_task_blocked_when_not_at_main(monkeypatch):
    """普通任务仍然要先尝试回主界面；回不去就跳过（不能带病继续跑）。"""
    import Goldenhandmaidens as gh

    stub, calls = _gate_stub(monkeypatch, ensure_result=False)
    skipped = gh.GameBotGUI._skip_task_when_not_at_main(
        stub, _Script("邮件", True), 1, 1, 0.0)
    assert skipped is True
    assert calls, "普通任务必须尝试回主界面"
    assert any("未回到主界面" in m for m in stub.logs), stub.logs
