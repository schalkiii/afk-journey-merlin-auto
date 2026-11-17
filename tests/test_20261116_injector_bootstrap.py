"""2026-11-16 定时冷启动「start 点击落空」三处修复的测试。

负验证留痕（把对应修复改回去，下列用例必须变红）：
- 删掉 `_run_login_before_flow` 里的 `_ensure_clicker_ready()` 调用 →
  `test_login_bootstraps_clicker_before_main` 必须失败；
- 把 `_click_start_with_confirm` 改回裸 `wait_and_click` →
  `test_click_start_retries_when_screen_unchanged` / `test_click_start_fails_after_all_attempts`
  必须失败；
- 把 `send_coord` 首次未消费的告警删掉 → `test_send_coord_warns_on_first_miss` 必须失败；
- 把 `_ensure_clicker_ready` 里的 `clear_stale_coord()` 删掉 →
  `test_ensure_clicker_ready_clears_stale_coord_first` 必须失败。
"""
import common
import Goldenhandmaidens as gh
import start


class _SyncThreadFactory:
    """把后台线程改成同步执行，让 worker 里的断言可确定。"""

    @staticmethod
    def Thread(target, *_a, **_k):
        class _Thread:
            def start(self):
                target()

        return _Thread()


class _Clock:
    """每次取时间前进固定步长，避免测试因真实 deadline 挂住。"""

    def __init__(self, step=1.0):
        self.t = 0.0
        self.step = step

    def __call__(self):
        self.t += self.step
        return self.t


class _Root:
    def after(self, _delay, fn, *args):
        fn(*args)


# ---------- 前置登录前必须先让注入器就绪 ----------

def test_login_bootstraps_clicker_before_main(monkeypatch):
    """注入器就绪检查必须发生在 start.main() 之前，否则 start 点击无人消费。"""
    order = []
    monkeypatch.setattr(gh, "threading", _SyncThreadFactory)
    monkeypatch.setattr(start, "main", lambda: order.append("main") or True)

    class Stub:
        _run_login_before_flow = gh.GameBotGUI._run_login_before_flow

        def __init__(self):
            self.root = _Root()

        def log(self, _msg):
            pass

        def _ensure_clicker_ready(self):
            order.append("clicker")
            return True

        def start_all(self):
            order.append("start_all")

        def stop_all(self):
            pass

    gh.GameBotGUI._run_login_before_flow(Stub())
    assert order == ["clicker", "main", "start_all"], order


def test_ensure_clicker_ready_clears_stale_coord_first(monkeypatch):
    """复用/启动注入器之前先清掉陈旧坐标，避免新注入器上线误点旧位置。"""
    calls = []
    monkeypatch.setattr(common, "clear_stale_coord",
                        lambda: calls.append("clear") or True)
    monkeypatch.setattr(common, "clicker_session_mismatch", lambda: None)
    monkeypatch.setattr(common, "_click_title_bar", lambda: True)

    class Stub:
        _ensure_clicker_ready = gh.GameBotGUI._ensure_clicker_ready

        def log(self, _msg):
            pass

        def is_click_from_file_running(self):
            return True

        def _launch_clicker(self, kill_ahk=False):
            calls.append("launch")
            return True

        def _warn_if_not_elevated(self):
            calls.append("warn")

    assert Stub()._ensure_clicker_ready() is True
    assert calls[0] == "clear", calls
    assert "warn" in calls


# ---------- start 点击必须校验界面变化并补点 ----------

def test_click_start_retries_when_screen_unchanged(monkeypatch):
    """点击后仍停在 start 界面就补点，不能像旧逻辑那样一次落空就当成功。"""
    clicked = []
    clock = _Clock(step=0.5)
    monkeypatch.setattr(start, "_find", lambda *_a, **_k: (100, 200))
    monkeypatch.setattr(start, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(start, "click_position", lambda pos, **_k: clicked.append(pos))
    monkeypatch.setattr(start, "wait_until_loaded", lambda *_a, **_k: None)
    monkeypatch.setattr(start.time, "time", clock)
    monkeypatch.setattr(start.time, "sleep", lambda _s: None)

    assert start._click_start_with_confirm("start", attempts=3) is False
    assert len(clicked) == 3, "三次都无变化才算失败，不能一次就放弃"


def test_click_start_fails_after_all_attempts(monkeypatch):
    """补点耗尽仍无变化必须返回 False，让登录流程如实按失败熔断。"""
    clock = _Clock(step=0.5)
    monkeypatch.setattr(start, "_find", lambda *_a, **_k: (100, 200))
    monkeypatch.setattr(start, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(start, "click_position", lambda *_a, **_k: None)
    monkeypatch.setattr(start, "wait_until_loaded", lambda *_a, **_k: None)
    monkeypatch.setattr(start.time, "time", clock)
    monkeypatch.setattr(start.time, "sleep", lambda _s: None)

    assert start._click_start_with_confirm("start", attempts=2) is False


def test_click_start_succeeds_when_start_disappears(monkeypatch):
    """点击后 start 消失即视为生效，不必等到主界面（加载期不该误判失败）。"""
    state = {"visible": True}
    clicked = []

    def fake_find(path, *_a, **_k):
        if str(path) == "start":
            return (100, 200) if state["visible"] else None
        return None

    monkeypatch.setattr(start, "_find", fake_find)
    monkeypatch.setattr(start, "log", lambda *_a, **_k: None)

    def fake_click(pos, **_k):
        clicked.append(pos)
        state["visible"] = False

    monkeypatch.setattr(start, "click_position", fake_click)
    monkeypatch.setattr(start, "wait_until_loaded", lambda *_a, **_k: None)
    monkeypatch.setattr(start.time, "sleep", lambda _s: None)

    assert start._click_start_with_confirm("start", attempts=3) is True
    assert clicked == [(100, 200)]


# ---------- 注入器失效尽早暴露 ----------

def test_send_coord_warns_when_sendinput_fails(monkeypatch):
    """2026-11-17 进程内注入后，SendInput 失败要当场记日志（替代旧「坐标无人消费」告警）。"""
    messages = []
    monkeypatch.setattr(common, "log", lambda m: messages.append(m))
    monkeypatch.setattr(common, "_restore_cursor", {"enabled": False})
    monkeypatch.setattr(common, "check_stop", lambda: None)
    monkeypatch.setattr(common, "ensure_game_clickable", lambda: True)
    monkeypatch.setattr(common, "point_owned_by_game", lambda *_a: True)
    monkeypatch.setattr(common, "_write_coord_raw", lambda *_a, **_k: False)

    common.send_coord(100, 200)
    assert any("注入失败" in m for m in messages), messages


def test_clear_stale_coord_removes_ipc_file(tmp_path, monkeypatch):
    """清理陈旧坐标：存在则删除并返回 True，不存在则返回 False。"""
    path = tmp_path / "target_coord.txt"
    path.write_text("2940 811", encoding="utf-8")
    monkeypatch.setattr(common, "coord_path", str(path))

    assert common.clear_stale_coord() is True
    assert not path.exists()
    assert common.clear_stale_coord() is False
