"""「跑完退出工具 / 跑完关闭游戏」两个收尾开关的回归测试。

用户 2026-11-16 需求：脚本跑完后按配置自动退出本工具、并关闭游戏客户端（典型场景是
定时无人值守，跑完让机器自己收摊）。覆盖四层：

- `bot_runtime.close_game` 的四条出口：没有窗口算成功、WM_CLOSE 后窗口消失、超时后强杀
  （taskkill 命令形状）、强杀被拒（提权不足）时如实报失败；
- 收尾判定 `_should_run_cleanup`：单独运行 / 被 F9 停止 / 两个开关都没勾都不触发；
- 收尾执行体：先关游戏再退工具，且关游戏不在主线程做（否则界面和 F9 一起冻住）；
- 退出路径 `_shutdown` 必须依次摘热键 → 回收注入器 → 销毁窗口，且自动退出不弹确认框。

不建游戏、不真关窗口、不销毁会话级 Tk 根（`_quit_now` 一律用替身宿主验证），也不联网。
"""
import contextlib
import json
import os
import pathlib
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")

import bot_runtime
import Goldenhandmaidens as gui


class _Done:
    """subprocess 结果的最小替身：close_game 只认返回码。"""

    def __init__(self, code=0):
        self.returncode = code


def _window_sequence(*handles):
    """按调用次序吐出窗口句柄的假 `_find_game_window`；序列用完后一直吐最后一个值。

    `close_game` 会查两次窗口（发消息前后各一次），死板地返回同一个值没法表达
    「发完 WM_CLOSE 窗口就没了」。
    """
    seq = list(handles)

    def fake():
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return fake


# ===== 关闭游戏 =====

def test_close_game_without_window_is_a_noop(monkeypatch):
    """游戏没开时不能算失败：定时任务跑完顺手关游戏，本来就可能什么都没开。"""
    monkeypatch.setattr(bot_runtime, "_find_game_window", lambda: None)
    kills = []
    monkeypatch.setattr(bot_runtime, "run_hidden",
                        lambda *a, **k: kills.append(a) or _Done(0))

    ok, msg = bot_runtime.close_game()

    assert ok is True
    assert "无需关闭" in msg
    assert kills == [], "没有窗口就不该去 taskkill"


def test_close_game_asks_window_first_and_reports_graceful_exit(monkeypatch):
    """先发 WM_CLOSE 让客户端正常退出；窗口消失就不补强杀。"""
    posted = []
    monkeypatch.setattr(bot_runtime, "_find_game_window", _window_sequence(111, None))
    monkeypatch.setattr(bot_runtime, "game_window_pid", lambda: 4242)
    monkeypatch.setattr(bot_runtime, "_post_close_message",
                        lambda hwnd: posted.append(hwnd) or True)
    monkeypatch.setattr(bot_runtime, "run_hidden",
                        lambda *a, **k: pytest.fail("正常退出后不得强杀"))

    ok, msg = bot_runtime.close_game()

    assert posted == [111], "必须对着游戏窗口发 WM_CLOSE"
    assert ok is True
    assert "正常退出" in msg


def test_close_game_force_kills_whole_tree_when_window_survives(monkeypatch):
    """窗口扛着 WM_CLOSE 不走（会弹「确认退出」的版本）时补一次强杀，且要杀整棵树。"""
    monkeypatch.setattr(bot_runtime, "_find_game_window", lambda: 111)
    monkeypatch.setattr(bot_runtime, "game_window_pid", lambda: 4242)
    monkeypatch.setattr(bot_runtime, "_post_close_message", lambda hwnd: True)
    kills = []
    monkeypatch.setattr(bot_runtime, "run_hidden",
                        lambda cmd, **k: kills.append(list(cmd)) or _Done(0))

    ok, msg = bot_runtime.close_game(timeout=0)

    assert ok is True
    assert "强制" in msg
    assert kills == [["taskkill", "/F", "/T", "/PID", "4242"]], "强杀必须带 /F /T /PID"


def test_close_game_without_pid_reports_failure(monkeypatch):
    """取不到进程号时不能假装成功——否则收尾日志会骗人。"""
    monkeypatch.setattr(bot_runtime, "_find_game_window", lambda: 111)
    monkeypatch.setattr(bot_runtime, "game_window_pid", lambda: None)
    monkeypatch.setattr(bot_runtime, "_post_close_message", lambda hwnd: True)

    ok, msg = bot_runtime.close_game(timeout=0)

    assert ok is False
    assert "进程号" in msg


def test_close_game_reports_failure_when_kill_denied(monkeypatch):
    """游戏以管理员运行时普通权限 taskkill 会被拒，必须如实报失败并提示提权。"""
    monkeypatch.setattr(bot_runtime, "_find_game_window", lambda: 111)
    monkeypatch.setattr(bot_runtime, "game_window_pid", lambda: 4242)
    monkeypatch.setattr(bot_runtime, "_post_close_message", lambda hwnd: True)
    monkeypatch.setattr(bot_runtime, "run_hidden", lambda cmd, **k: _Done(5))

    ok, msg = bot_runtime.close_game(timeout=0)

    assert ok is False
    assert "管理员" in msg


# ===== 收尾判定 =====

class _CleanupHost:
    """只带判定所需成员的最小替身。"""

    def __init__(self, quit_after_run=False, close_game_after_run=False, stopped=False):
        self.quit_after_run = quit_after_run
        self.close_game_after_run = close_game_after_run
        self.stop_event = threading.Event()
        if stopped:
            self.stop_event.set()


@pytest.mark.parametrize("quit_app,close_game", [
    (True, False),
    (False, True),
    (True, True),
])
def test_cleanup_runs_when_configured_and_run_finished(quit_app, close_game):
    host = _CleanupHost(quit_after_run=quit_app, close_game_after_run=close_game)

    assert gui.GameBotGUI._should_run_cleanup(host, auto_cleanup=True) is True


def test_cleanup_is_skipped_when_both_switches_are_off():
    host = _CleanupHost()

    assert gui.GameBotGUI._should_run_cleanup(host, auto_cleanup=True) is False


def test_cleanup_is_skipped_for_single_script_runs():
    """「只运行当前功能」是手动补跑，把工具关掉会打断用户接下来的操作。"""
    host = _CleanupHost(quit_after_run=True, close_game_after_run=True)

    assert gui.GameBotGUI._should_run_cleanup(host, auto_cleanup=False) is False


def test_cleanup_is_skipped_after_f9_stop():
    """F9 停止说明用户就在跟前，这时关游戏正好关掉他要看的界面。"""
    host = _CleanupHost(quit_after_run=True, close_game_after_run=True, stopped=True)

    assert gui.GameBotGUI._should_run_cleanup(host, auto_cleanup=True) is False


# ===== 退出路径 =====

class _ShutdownHost:
    """记录退出动作次序的替身：root 指向自己，避免碰会话级 Tk 根。"""

    def __init__(self):
        self.calls = []
        self.root = self

    def _unregister_hotkeys(self):
        self.calls.append("hotkeys")

    def _stop_clicker(self):
        self.calls.append("clicker")

    def destroy(self):
        self.calls.append("destroy")


def test_shutdown_unregisters_hotkeys_and_recycles_clicker():
    """漏一步就留下长期残留：注入器会把坐标读走、点击却打到别的桌面。"""
    host = _ShutdownHost()

    gui._shutdown_app(host)

    assert host.calls == ["hotkeys", "clicker", "destroy"]


def test_quit_after_run_never_asks_for_confirmation(monkeypatch):
    """跑完自动退出是用户勾的开关，不该再弹「脚本正在运行中，确定退出吗」。"""
    prompts = []
    monkeypatch.setattr(gui.messagebox, "askokcancel",
                        lambda *a, **k: prompts.append(a) or False)

    host = _ShutdownHost()
    gui.GameBotGUI._quit_now(host)

    assert prompts == []
    assert host.calls == ["hotkeys", "clicker", "destroy"]


# ===== 收尾执行体 =====

@pytest.fixture
def make_app(tk_root, monkeypatch, tmp_path):
    """按需构造 GUI 实例的工厂（同一会话共用一个 Tk 根）。"""
    monkeypatch.setattr(gui.GameBotGUI, "_register_hotkeys", lambda _self: None)
    monkeypatch.setattr(gui.GameBotGUI, "_auto_check_update", lambda _self: None)
    created = []

    def _make(config=None):
        path = tmp_path / "game_bot_config.json"
        if config is not None:
            path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(bot_runtime, "CONFIG_FILE", str(path))
        instance = gui.GameBotGUI(tk_root)
        monkeypatch.setattr(instance, "log", lambda _msg: None)
        created.append(instance)
        return instance

    yield _make
    for instance in created:
        with contextlib.suppress(Exception):
            instance._unregister_hotkeys()
    for child in list(tk_root.winfo_children()):
        child.destroy()


def test_options_default_to_off(make_app):
    app = make_app()

    assert app.quit_after_run is False, "默认不退出：手动跑的人还要看日志"
    assert app.close_game_after_run is False
    assert app.quit_after_run_check.label_text == "跑完退出工具"
    assert app.close_game_after_run_check.label_text == "跑完关闭游戏"


def test_options_restore_from_config(make_app):
    app = make_app({"quit_after_run": True, "close_game_after_run": True})

    assert app.quit_after_run_var.get() is True
    assert app.close_game_after_run_var.get() is True


def test_toggling_checkboxes_persists_both_flags(make_app, tmp_path):
    app = make_app()

    app.quit_after_run_check.toggle()
    app.close_game_after_run_check.toggle()

    saved = json.loads((tmp_path / "game_bot_config.json").read_text(encoding="utf-8"))
    assert saved["quit_after_run"] is True
    assert saved["close_game_after_run"] is True


def test_enabling_quit_warns_when_daily_schedule_is_active(make_app, monkeypatch):
    """定时循环活在工具进程里：勾了「跑完退出工具」，第二天的定时就不存在了。"""
    app = make_app()
    app.schedule_active = True
    messages = []
    monkeypatch.setattr(app, "log", messages.append)

    app.quit_after_run_check.toggle()

    assert any("定时" in m and "不会再触发" in m for m in messages), messages


def test_cleanup_worker_closes_game_then_quits(make_app, monkeypatch):
    app = make_app()
    app.close_game_after_run = True
    app.quit_after_run = True
    messages = []
    monkeypatch.setattr(app, "log", messages.append)
    closed = []
    monkeypatch.setattr(gui, "close_game",
                        lambda: closed.append(True) or (True, "已关闭游戏（正常退出）"))
    scheduled = []
    monkeypatch.setattr(app.root, "after",
                        lambda delay, func: scheduled.append((delay, func)))

    app._after_run_cleanup_worker()

    assert closed == [True]
    assert "已关闭游戏（正常退出）" in messages
    assert scheduled == [(0, app._quit_now)], "关完游戏必须把退出动作交回主线程"


def test_cleanup_worker_skips_game_close_when_only_quit_is_enabled(make_app, monkeypatch):
    app = make_app()
    app.close_game_after_run = False
    app.quit_after_run = True
    monkeypatch.setattr(app, "log", lambda _msg: None)
    monkeypatch.setattr(gui, "close_game",
                        lambda: pytest.fail("没勾「跑完关闭游戏」就不许动游戏"))
    scheduled = []
    monkeypatch.setattr(app.root, "after",
                        lambda delay, func: scheduled.append((delay, func)))

    app._after_run_cleanup_worker()

    assert [func for _delay, func in scheduled] == [app._quit_now]


def test_cleanup_worker_keeps_running_when_quit_is_off(make_app, monkeypatch):
    app = make_app()
    app.close_game_after_run = True
    app.quit_after_run = False
    monkeypatch.setattr(app, "log", lambda _msg: None)
    monkeypatch.setattr(gui, "close_game", lambda: (True, "已关闭游戏（正常退出）"))
    scheduled = []
    monkeypatch.setattr(app.root, "after",
                        lambda delay, func: scheduled.append((delay, func)))

    app._after_run_cleanup_worker()

    assert scheduled == [], "只勾了关游戏时工具必须留着"


def test_cleanup_runs_off_the_main_thread(make_app, monkeypatch):
    """关游戏要等窗口消失（最长十几秒），放主线程会把界面连同 F9 一起冻住。"""
    app = make_app()
    started = []

    class _Thread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            self.daemon = daemon

        def start(self):
            started.append((self.target, self.daemon))

    monkeypatch.setattr(gui.threading, "Thread", _Thread)

    app._after_run_cleanup()

    assert started == [(app._after_run_cleanup_worker, True)]


def test_run_loop_decides_cleanup_before_scheduling_stop():
    """判定必须在调度 stop_all 之前取值：stop_all 自己会把 stop_event 置位。

    这条改动藏在运行循环尾部，真跑一遍要好几分钟，只能按源码次序守住。
    """
    source = pathlib.Path(gui.__file__).read_text(encoding="utf-8")
    tail = source[source.index("def run_scripts_thread("):source.index("def _enqueue_log(")]

    assert "_should_run_cleanup(auto_cleanup)" in tail
    assert tail.index("_should_run_cleanup(") < tail.index("self.root.after(0, self.stop_all)")
    assert "self.root.after(300, self._after_run_cleanup)" in tail
