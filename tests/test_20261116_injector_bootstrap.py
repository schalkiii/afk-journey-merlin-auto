"""2026-11-16 定时冷启动「start 点击落空」三处修复的测试。

负验证留痕（把对应修复改回去，下列用例必须变红）：
- 删掉 `_run_login_before_flow` 里的 `_ensure_clicker_ready()` 调用 →
  `test_login_bootstraps_clicker_before_main` 必须失败；
- 把 `_click_start_with_confirm` 改回裸 `wait_and_click` →
  `test_click_start_retries_when_screen_unchanged` / `test_click_start_fails_after_all_attempts`
  必须失败；
- 把 `send_coord` 注入失败的告警删掉 → `test_send_coord_warns_when_sendinput_fails` 必须失败；
- 把 `_ensure_clicker_ready` 里的提权告警删掉 →
  `test_ensure_clicker_ready_only_warns_about_elevation` 必须失败。

（2026-11-17 点击改进程内 SendInput 后，「清陈旧坐标 / 复用已在跑的注入器」这两条
用例随机制一起删除：没有中间进程，也就没有陈旧坐标会被误点。）
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


def test_ensure_clicker_ready_only_warns_about_elevation(monkeypatch):
    """进程内注入没有「启动注入器」这一步：就绪检查只剩提权告警，且恒为就绪。"""
    calls = []

    class Stub:
        _ensure_clicker_ready = gh.GameBotGUI._ensure_clicker_ready

        def log(self, _msg):
            pass

        def _warn_if_not_elevated(self):
            calls.append("warn")
            return False

    assert Stub()._ensure_clicker_ready() is True
    assert calls == ["warn"]


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
