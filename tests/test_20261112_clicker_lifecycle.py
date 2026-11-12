"""2026-11-12 注入器生命周期：退出工具必须把**自己启动的**注入器一起收掉。

背景（实机踩到）：本机装了 AHK v2，`_resolve_clicker_launcher()` 优先走明文脚本，
注入器进程名是 **AutoHotkey64.exe**；而 `on_closing` 原先只
`taskkill /IM click_from_file.exe` —— 名字对不上，一个都杀不到。
于是 session 3（RDP）里启动的注入器一直残留，后续所有点击都
「坐标被消费、游戏毫无反应」，排查了一整轮。

负验证留痕（改回旧实现必须失败）：
- `_stop_clicker` 去掉「按记录的 PID 杀」分支（退回只按镜像名）→
  `test_stop_clicker_kills_recorded_pid` 必须失败；
- `_launch_clicker` 不再记录 `proc.pid` →
  `test_launch_clicker_records_pid` 必须失败。
"""
import Goldenhandmaidens as gh


class _Done:
    def __init__(self, rc=0):
        self.stdout = b""
        self.returncode = rc


class FakeHost:
    """只带注入器相关成员的宿主，避免构造整个 Tk 窗口。"""

    def __init__(self, pid=None, is_clicker=True):
        self._clicker_pid = pid
        self.logs = []
        self.stops = []
        self._is_clicker = is_clicker
        self._resolve_clicker_launcher = lambda: ["AutoHotkey64.exe", "click_from_file.ahk"]

    def log(self, msg):
        self.logs.append(msg)

    def _pid_is_clicker(self, pid):
        return self._is_clicker

    def _taskkill(self, args):
        return gh.GameBotGUI._taskkill(args)

    def _stop_clicker(self, kill_ahk=False):
        self.stops.append(kill_ahk)
        self._clicker_pid = None


def _patch(monkeypatch, host, recorded):
    def fake_run(cmd, **_kwargs):
        recorded.append(list(cmd))
        return _Done()

    monkeypatch.setattr(gh.subprocess, "run", fake_run)
    monkeypatch.setattr(gh.time, "sleep", lambda _s: None)


def test_stop_clicker_kills_recorded_pid(monkeypatch):
    """注入器是 AHK 明文脚本时进程名叫 AutoHotkey64.exe，只能靠 PID 精确回收。"""
    host = FakeHost(pid=4321)
    calls = []
    _patch(monkeypatch, host, calls)

    gh.GameBotGUI._stop_clicker(host)

    pid_calls = [c for c in calls if "/PID" in c]
    assert pid_calls, f"必须按 PID 杀一次，实际调用: {calls}"
    assert "4321" in pid_calls[0]
    assert host._clicker_pid is None, "杀完要清掉记录，避免下一轮误杀复用的 PID"


def test_stop_clicker_skips_foreign_pid(monkeypatch):
    """记录的 PID 已被系统复用给别的程序时，绝不能照杀 —— 会打到无关进程。"""
    host = FakeHost(pid=999, is_clicker=False)
    calls = []
    _patch(monkeypatch, host, calls)

    gh.GameBotGUI._stop_clicker(host)

    assert not [c for c in calls if "/PID" in c], f"不该按 PID 杀: {calls}"
    assert any("click_from_file.exe" in c for c in calls), "镜像名兜底仍然要清一次"


def test_stop_clicker_without_pid_still_cleans_by_name(monkeypatch):
    """没记录到 PID（例如复用外部注入器）时仍按镜像名兜底，不能什么都不做。"""
    host = FakeHost(pid=None)
    calls = []
    _patch(monkeypatch, host, calls)

    gh.GameBotGUI._stop_clicker(host)

    assert any("click_from_file.exe" in c for c in calls), calls


class _Root:
    """够用的 root 替身：只关心 destroy 有没有被调用。"""

    def __init__(self):
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


def test_on_closing_stops_clicker(monkeypatch):
    """点窗口 X 关闭时必须走统一回收；旧实现只 taskkill click_from_file.exe，
    AHK 明文脚本模式的注入器名字对不上，一个都杀不到。"""
    host = FakeHost()
    host.root = _Root()
    host.is_running = False
    host._unregister_hotkeys = lambda: None

    gh.GameBotGUI.on_closing(host)

    assert host.stops == [False], "on_closing 必须调用 _stop_clicker"
    assert host.root.destroyed is True


def test_stop_clicker_warns_when_kill_denied(monkeypatch):
    """提权启动的注入器普通权限杀不掉：必须留痕，静默失败会让下次误复用。"""
    host = FakeHost(pid=555)
    calls = []

    def deny(cmd, **_kwargs):
        calls.append(list(cmd))
        return _Done(5 if "/PID" in cmd else 0)

    monkeypatch.setattr(gh.subprocess, "run", deny)
    monkeypatch.setattr(gh.time, "sleep", lambda _s: None)

    gh.GameBotGUI._stop_clicker(host)

    assert any("无法结束注入器" in m for m in host.logs), host.logs


def test_launch_clicker_records_pid(monkeypatch):
    """启动后必须记下 PID，否则退出时无从精确回收。"""
    class FakeProc:
        pid = 7777

    monkeypatch.setattr(gh.subprocess, "Popen", lambda *_a, **_k: FakeProc())
    monkeypatch.setattr(gh, "get_work_path", lambda _p: "D:/workspace")
    monkeypatch.setattr(gh.time, "sleep", lambda _s: None)

    host = FakeHost()
    assert gh.GameBotGUI._launch_clicker(host) is True
    assert host._clicker_pid == 7777
    assert any("7777" in m for m in host.logs), host.logs


def test_launch_clicker_cleans_previous_before_restart(monkeypatch):
    """重启前先收掉旧的，否则会留下两份注入器抢同一个坐标文件。"""
    class FakeProc:
        pid = 8888

    monkeypatch.setattr(gh.subprocess, "Popen", lambda *_a, **_k: FakeProc())
    monkeypatch.setattr(gh, "get_work_path", lambda _p: "D:/workspace")
    monkeypatch.setattr(gh.time, "sleep", lambda _s: None)

    host = FakeHost(pid=1111)
    gh.GameBotGUI._launch_clicker(host, kill_ahk=True)
    assert host.stops == [True], "重启前必须调用一次回收（并透传 kill_ahk）"
    assert host._clicker_pid == 8888


def test_warns_when_not_elevated(monkeypatch):
    """非管理员运行必须告警：游戏提权时 SendInput 会被 UIPI 静默丢弃，
    表现是「点击判据全成立、画面不动、每个任务超时」，日志里没有任何异常。"""
    monkeypatch.setattr(gh.common, "is_process_elevated", lambda: False)

    host = FakeHost()
    assert gh.GameBotGUI._warn_if_not_elevated(host) is True
    assert any("管理员" in m for m in host.logs), host.logs


def test_silent_when_elevated(monkeypatch):
    monkeypatch.setattr(gh.common, "is_process_elevated", lambda: True)

    host = FakeHost()
    assert gh.GameBotGUI._warn_if_not_elevated(host) is False
    assert host.logs == []
