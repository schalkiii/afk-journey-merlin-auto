"""运行状态复位与「开始运行 / 立即开始」语义的回归测试。

覆盖两类回归：
- 未勾选 / 不在本轮列表的功能不能停在「排队」（等待中），旧失败态也要清掉；
- 游戏已在运行时「开始运行 (F8)」不得重复拉起客户端，而「立即开始」保持纯运行。
测试不建游戏、不起真实运行线程。
"""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")

import bot_runtime
import Goldenhandmaidens as gui


class _FakeRunGui:
    """只带运行控制所需成员的最小替身，避免真建 Tk 界面与工作线程。"""

    def __init__(self, scripts):
        self.scripts = scripts
        self.is_running = False
        self.stop_event = threading.Event()
        self.logs = []
        self.current_task = None

    def log(self, message):
        self.logs.append(message)

    def update_master_button(self):
        pass

    def update_script_panel(self):
        pass

    def _set_current_task(self, name):
        self.current_task = name


def _make_scripts(statuses):
    """按 (名称, 是否勾选, 初始状态) 建假 ScriptConfig，只用于状态逻辑测试。"""
    scripts = [gui.ScriptConfig(name, enabled=enabled) for name, enabled, _ in statuses]
    for script, (_, _, status) in zip(scripts, statuses):
        script.status = status
    return scripts


def test_prepare_marks_only_scripts_in_this_run_as_pending():
    scripts = _make_scripts([
        ("甲", True, "失败"),
        ("乙", False, "错误"),
        ("丙", True, "完成"),
    ])
    fake = _FakeRunGui(scripts)

    # 本轮只包含甲、丙；乙未勾选且不在列表里
    gui.GameBotGUI._prepare_run_statuses(fake, [scripts[0], scripts[2]])

    assert scripts[0].status == "等待中"
    assert scripts[2].status == "等待中"
    assert scripts[1].status == "就绪", "未勾选的功能不能残留「排队」"
    assert scripts[0].status != "失败", "上一轮的失败态必须被清掉"
    assert scripts[2].status != "完成"


def test_prepare_respect_enabled_false_marks_only_passed_script():
    scripts = _make_scripts([
        ("甲", False, "失败"),
        ("乙", False, "错误"),
    ])
    fake = _FakeRunGui(scripts)

    gui.GameBotGUI._prepare_run_statuses(fake, [scripts[0]], respect_enabled=False)

    assert scripts[0].status == "等待中", "单跑当前功能时忽略勾选，只标传进来的那个"
    assert scripts[1].status == "就绪"


def test_stop_all_resets_pending_to_ready():
    scripts = _make_scripts([
        ("运行中的", True, "运行中"),
        ("排队的", True, "等待中"),
        ("完成的", True, "完成"),
        ("失败的", True, "失败"),
    ])
    fake = _FakeRunGui(scripts)

    gui.GameBotGUI.stop_all(fake)

    assert scripts[0].status == "已停止"
    assert scripts[1].status == "就绪", "停止后不能留下排队状态"
    assert scripts[2].status == "完成", "已结束的任务状态不应被停止动作改写"
    assert scripts[3].status == "失败"


@pytest.fixture
def root(tk_root):
    """共用 conftest 的会话级 Tk 根，避免同进程反复建根导致随机 TclError。"""
    return tk_root


@pytest.fixture
def app(root, monkeypatch, tmp_path):
    monkeypatch.setattr(bot_runtime, "CONFIG_FILE", str(tmp_path / "game_bot_config.json"))
    instance = gui.GameBotGUI(root)
    monkeypatch.setattr(instance, "log", lambda _msg: None)
    yield instance
    instance._unregister_hotkeys()
    for child in list(root.winfo_children()):
        child.destroy()


@pytest.fixture
def scheduled(monkeypatch):
    """记录 root.after 的调度，不真正等延迟。"""
    calls = []

    def fake_after(delay, func):
        calls.append((delay, func))

    return calls, fake_after


def test_launch_then_start_skips_launch_when_game_already_running(
        app, monkeypatch, scheduled):
    calls, fake_after = scheduled
    launched = []
    monkeypatch.setattr(gui, "is_game_running", lambda: True)
    monkeypatch.setattr(app, "launch_game_from_shortcut", lambda: launched.append("launch"))
    monkeypatch.setattr(app.root, "after", fake_after)
    app.game_launch_delay = 30
    app.scripts[0].enabled = True

    app.launch_game_then_start(launch_game=True)

    assert launched == [], "游戏已在运行时不得重复启动客户端"
    assert calls[0][0] == 0, "已在运行应立即开始，不再等待启动延迟"


def test_launch_then_start_launches_when_game_not_running(app, monkeypatch, scheduled):
    calls, fake_after = scheduled
    launched = []
    monkeypatch.setattr(gui, "is_game_running", lambda: False)
    monkeypatch.setattr(app, "launch_game_from_shortcut", lambda: launched.append("launch"))
    monkeypatch.setattr(app.root, "after", fake_after)
    app.game_launch_delay = 5
    app.scripts[0].enabled = True

    app.launch_game_then_start(launch_game=True)

    assert launched == ["launch"]
    assert calls[0][0] == 5000, "未运行时应按配置的启动等待秒数调度"


def test_launch_then_start_without_launch_flag_does_not_start_game(
        app, monkeypatch, scheduled):
    calls, fake_after = scheduled
    launched = []
    monkeypatch.setattr(gui, "is_game_running", lambda: False)
    monkeypatch.setattr(app, "launch_game_from_shortcut", lambda: launched.append("launch"))
    monkeypatch.setattr(app.root, "after", fake_after)
    app.scripts[0].enabled = True

    app.launch_game_then_start(launch_game=False)

    assert launched == []
    assert calls[0][0] == 0


def test_start_all_is_run_only_and_never_launches_game(app, monkeypatch):
    begun = []
    monkeypatch.setattr(app, "launch_game_from_shortcut", lambda: begun.append("launch"))
    monkeypatch.setattr(
        app, "_begin_run",
        lambda scripts, respect_enabled=True: begun.append(("run", scripts, respect_enabled)),
    )
    app.scripts[0].enabled = True

    app.start_all()

    assert "launch" not in begun, "start_all 只运行脚本，不碰启动器"
    assert begun[0][0] == "run"
    assert begun[0][1] == [s for s in app.scripts if s.enabled]
    assert begun[0][2] is True
