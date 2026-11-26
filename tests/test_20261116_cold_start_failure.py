"""2026-11-16 定时冷启动连锁失败的三处修复。

负验证留痕（把对应修复改回去，下列用例必须变红）：
- 删掉 `start._wait_for_start` 的「可交互弹窗」分支 →
  `test_wait_for_start_skips_when_only_popup` 必须失败（会白等满 180 秒）；
- 把登录失败后的熔断改回「仍继续执行任务列表」→
  `test_login_failure_circuit_breaks_when_unrecoverable` 必须失败；
- 去掉运行循环里的连续跳过计数 →
  `test_run_loop_has_main_gate_circuit_break` 必须失败。
"""
import inspect

import Goldenhandmaidens as gh
import start


class _Clock:
    """可手动推进的假时钟：`time()` 只读当前值，只有 `sleep()` 会推进。

    旧实现「每取一次时间就 +10 秒」对调用次数敏感：time 是全局模块，同一进程里
    别的线程（日志、看门狗）也可能调到被替换的 `time.time()`，多一次调用就把
    30 秒预算吃满——2026-11-26 push 门禁实测偶发 `assert 30.0 < 30` 判红。
    改成只由 sleep 推进后，「第一轮就识别弹窗」必然停在 0，「没有弹窗要等满」
    则按 0.5 秒一步步走到 timeout，两条路径都不再依赖调用次数。
    """

    def __init__(self, step=0.5):
        self.t = 0.0
        self.step = step

    def time(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


# ---------- 登录判据：可交互弹窗 = 已越过开始界面 ----------

def test_wait_for_start_skips_when_only_popup(monkeypatch):
    """冷启动停在「点击空白处关闭」弹窗上，必须立刻转清理而不是白等 180 秒。"""
    clock = _Clock()

    def fake_find(path, *_a, **_k):
        if "dianjikongbaichuguanbi" in str(path):
            return (1129, 902)
        return None

    monkeypatch.setattr(start, "_find", fake_find)
    monkeypatch.setattr(start, "at_main_interface", lambda: False)
    monkeypatch.setattr(start, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(start.time, "time", clock.time)
    monkeypatch.setattr(start.time, "sleep", clock.sleep)

    assert start._wait_for_start("start", "yueka", "libao", timeout=30) is True
    assert clock.t < 30, "应当在第一轮就识别弹窗，不能循环到超时"


def test_wait_for_start_still_waits_without_popup(monkeypatch):
    """没有任何弹窗也没有 start 时不能误判已越过，仍要走满超时返回失败。"""
    clock = _Clock()
    monkeypatch.setattr(start, "_find", lambda *_a, **_k: None)
    monkeypatch.setattr(start, "at_main_interface", lambda: False)
    monkeypatch.setattr(start, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(start.time, "time", clock.time)
    monkeypatch.setattr(start.time, "sleep", clock.sleep)

    assert start._wait_for_start("start", "yueka", "libao", timeout=30) is False


def test_wait_for_start_prefers_real_start(monkeypatch):
    """start 与弹窗同时可见时优先点 start，避免跳过还没真正开始的会话。"""
    clicked = []
    state = {"start_visible": True}

    def fake_find(path, *_a, **_k):
        p = str(path)
        if p == "start":
            return (100, 200) if state["start_visible"] else None
        if "dianjikongbaichuguanbi" in p:
            return (1129, 902)
        return None

    monkeypatch.setattr(start, "_find", fake_find)
    monkeypatch.setattr(start, "at_main_interface", lambda: False)
    monkeypatch.setattr(start, "log", lambda *_a, **_k: None)

    def fake_click(pos, *_a, **_k):
        clicked.append(pos)
        state["start_visible"] = False  # 模拟点击生效：start 消失

    monkeypatch.setattr(start, "click_position", fake_click)
    monkeypatch.setattr(start, "wait_until_loaded", lambda *_a, **_k: None)
    monkeypatch.setattr(start.time, "sleep", lambda _s: None)

    assert start._wait_for_start("start", "yueka", "libao", timeout=30) is True
    assert clicked == [(100, 200)]


# ---------- 登录失败后的熔断 ----------

class _SyncThreadFactory:
    """把后台线程改成同步执行，让 worker 里的断言可确定。"""

    @staticmethod
    def Thread(target, *_a, **_k):
        class _Thread:
            def start(self):
                target()

        return _Thread()


def _login_stub(monkeypatch, *, login_ok, recover_ok):
    """只够 `_run_login_before_flow` 用的替身，记录是否开跑 / 是否熔断。"""
    monkeypatch.setattr(gh, "threading", _SyncThreadFactory)
    monkeypatch.setattr(start, "main", lambda: login_ok)
    counts = {"ensure": 0}

    def fake_ensure():
        counts["ensure"] += 1
        return recover_ok

    monkeypatch.setattr(gh.common, "ensure_main_interface", fake_ensure)

    class _Root:
        def after(self, _delay, fn, *args):
            fn(*args)

    class Stub:
        _run_login_before_flow = gh.GameBotGUI._run_login_before_flow

        def __init__(self):
            self.root = _Root()
            self.logs = []
            self.started = False
            self.stopped = False

        def log(self, msg):
            self.logs.append(msg)

        def _ensure_clicker_ready(self):
            return True

        def start_all(self):
            self.started = True

        def stop_all(self):
            self.stopped = True

    stub = Stub()
    gh.GameBotGUI._run_login_before_flow(stub)
    return stub, counts


def test_login_failure_circuit_breaks_when_unrecoverable(monkeypatch):
    """登录失败且强恢复不了：必须停本轮，不能让后续 15 项在错界面连败。"""
    stub, counts = _login_stub(monkeypatch, login_ok=False, recover_ok=False)
    assert stub.started is False
    assert stub.stopped is True
    assert counts["ensure"] == 1
    assert any("本轮停止" in m for m in stub.logs), stub.logs


def test_login_failure_continues_when_recovered(monkeypatch):
    """强恢复成功就照常开跑，不因登录结果误报而白停一轮。"""
    stub, counts = _login_stub(monkeypatch, login_ok=False, recover_ok=True)
    assert stub.started is True
    assert stub.stopped is False
    assert counts["ensure"] == 1


def test_login_success_skips_recovery(monkeypatch):
    """登录本来就成功时不要多调一次强恢复。"""
    stub, counts = _login_stub(monkeypatch, login_ok=True, recover_ok=False)
    assert stub.started is True
    assert counts["ensure"] == 0


# ---------- 连锁失败熔断 ----------

def test_run_loop_has_main_gate_circuit_break():
    """连续 N 项「未回到主界面」后必须熔断，否则每项空转 25 秒共耗 6 分钟。"""
    source = inspect.getsource(gh.GameBotGUI.run_scripts_thread)
    assert "consecutive_main_gate_failures" in source
    assert "MAIN_GATE_CIRCUIT_BREAK" in source
    assert 1 <= gh.MAIN_GATE_CIRCUIT_BREAK <= 5, gh.MAIN_GATE_CIRCUIT_BREAK
