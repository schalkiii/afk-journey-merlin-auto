"""任务切换前「回到主界面」的兜底契约（不启动运行线程、不碰游戏窗口）。

负验证留痕：
- 把 `ensure_main_interface()` 改回「忽略 recover 返回值、恒 True」，
  `test_ensure_main_interface_propagates_recover_failure` 必须失败；
- 把 `_skip_task_when_not_at_main` 里的 `continue` 判定删掉（恒 False），
  `test_skip_task_when_main_interface_unreachable` 必须失败；
- 把「登录」豁免去掉，`test_login_is_exempt_from_main_interface_check` 必须失败。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common
import Goldenhandmaidens as gui


def _stub_common(monkeypatch, at_main, recover=True):
    calls = []

    def fake_at_main():
        calls.append("at_main")
        return at_main

    def fake_recover():
        calls.append("recover")
        return recover

    monkeypatch.setattr(common, "dismiss_popup", lambda: calls.append("dismiss"))
    monkeypatch.setattr(common, "at_main_interface", fake_at_main)
    monkeypatch.setattr(common, "recover_to_main_interface", fake_recover)
    return calls


def test_ensure_main_interface_skips_recover_when_already_home(monkeypatch):
    calls = _stub_common(monkeypatch, at_main=True)
    assert common.ensure_main_interface() is True
    assert calls == ["dismiss", "at_main"]


def test_ensure_main_interface_propagates_recover_failure(monkeypatch):
    calls = _stub_common(monkeypatch, at_main=False, recover=False)
    assert common.ensure_main_interface() is False
    assert calls == ["dismiss", "at_main", "recover"]


class _FakeGui:
    """只带 `_skip_task_when_not_at_main` 所需成员的最小替身。"""

    def __init__(self):
        self.logs = []
        self.after_calls = []

    def log(self, message):
        self.logs.append(message)

    def update_script_panel(self):
        pass

    @property
    def root(self):
        return self

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))


def _fake_script(name="邮件"):
    script = gui.ScriptConfig(name, enabled=True)
    script.status = "排队中"
    return script


def test_skip_task_when_main_interface_unreachable(monkeypatch):
    _stub_common(monkeypatch, at_main=False, recover=False)
    monkeypatch.setattr(common, "capture_failure_context",
                        lambda *_a, **_k: None)
    fake, script = _FakeGui(), _fake_script()

    assert gui.GameBotGUI._skip_task_when_not_at_main(fake, script, 1, 1, 0.0) is True
    assert script.status == "失败"
    assert any("未回到主界面" in line for line in fake.logs)
    assert fake.after_calls, "跳过后仍要刷新状态色块"


def test_no_skip_when_main_interface_reachable(monkeypatch):
    _stub_common(monkeypatch, at_main=True)
    fake, script = _FakeGui(), _fake_script()

    assert gui.GameBotGUI._skip_task_when_not_at_main(fake, script, 1, 1, 0.0) is False
    assert script.status == "排队中"
    assert fake.logs == []


def test_login_is_exempt_from_main_interface_check(monkeypatch):
    calls = _stub_common(monkeypatch, at_main=False, recover=False)
    fake = _FakeGui()

    assert gui.GameBotGUI._skip_task_when_not_at_main(fake, _fake_script("登录"), 1, 1, 0.0) is False
    assert calls == [], "登录任务不应触发主界面兜底"


def test_recover_handles_trigger_event_page(monkeypatch):
    """翻翻乐「触发事件」选择页必须能从通用回退里退出。

    2026-11-18 实机：该页既没有返回箭头也没有空白关闭提示，通用回退空转 17 秒后
    静默失败，后续 4 个任务全部「开始前未回到主界面」连锁失败。
    """
    clicks = []
    state = {"shown": True, "main": False}

    def fake_find(template_path, *args, **kwargs):
        if state["shown"] and template_path.endswith("chufashijian.png"):
            return (760, 120)
        return None

    def fake_click(pos, wait=1.5, twice=False):
        clicks.append(pos)
        state["shown"] = False
        state["main"] = True

    monkeypatch.setattr(common, "check_stop", lambda: None)
    monkeypatch.setattr(common, "find_center_silent", fake_find)
    monkeypatch.setattr(common, "at_main_interface", lambda *a, **k: state["main"])
    monkeypatch.setattr(common, "click_position", fake_click)
    monkeypatch.setattr(common, "game_client_region", lambda *a, **k: (100, 50, 1600, 900))
    monkeypatch.setattr(common, "log", lambda *a, **k: None)

    assert common.recover_to_main_interface(max_tries=2) is True
    assert clicks == [(100 + 815, 50 + 606)]
