"""2026-11-17：鼠标注入从「AHK 独立进程 + txt 坐标」改为「进程内 SendInput」。

负验证留痕（把对应实现改回去，下列用例必须变红）：
- `inject_click` 改用 mouse_event 分离 DOWN/UP + sleep →
  `test_inject_click_uses_sendinput_atomically` 必须失败；
- `send_coord` 改回写坐标文件 → `test_no_module_keeps_coord_ipc_path` 必须失败；
- `inject_drag` 去掉 try/finally 里的 LEFTUP → `test_inject_drag_releases_left_button_on_exception`
  必须失败（进程中断会卡住左键）；
- `drag_utils.send_drag` 改回写 `shared/drag_coord.txt` →
  `test_drag_helpers_delegate_to_inject_drag` 必须失败。
"""
import pathlib

import pytest

import common
import drag_utils
import warehouse


def _stub_user32(monkeypatch, moves, fail_after=None):
    """替掉 user32：记录每次 SetCursorPos，可选在第 N 次调用时抛异常。"""

    class _User32:
        def SetCursorPos(self, x, y):
            moves.append((x, y))
            if fail_after is not None and len(moves) >= fail_after:
                raise OSError("cursor blocked")

    monkeypatch.setattr(common.ctypes, "windll", type("W", (), {"user32": _User32()}))


def _stub_send_events(monkeypatch, flags):
    """记录每次 SendInput 提交了哪些 flag，并报告「全部注入成功」。"""

    def fake_send(*f):
        flags.append(f)
        return len(f)

    monkeypatch.setattr(common, "_send_mouse_events", fake_send)


# ---------- 点击 ----------

def test_inject_click_uses_sendinput_atomically(monkeypatch):
    """DOWN/UP 必须在同一次 SendInput 调用里提交，避免中断卡住左键。"""
    moves, flags = [], []
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)
    _stub_user32(monkeypatch, moves)
    _stub_send_events(monkeypatch, flags)

    assert common.inject_click(123, 456) is True
    assert moves == [(123, 456)]
    assert flags == [(common.MOUSEEVENTF_LEFTDOWN, common.MOUSEEVENTF_LEFTUP)], \
        "按下+松开必须一次原子提交，不能分离成两次调用"


def test_inject_click_reports_failure(monkeypatch):
    """SendInput 返回的事件数不足时要报失败，让 send_coord 记告警。"""
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)
    _stub_user32(monkeypatch, [])
    monkeypatch.setattr(common, "_send_mouse_events", lambda *_a: 0)
    assert common.inject_click(1, 2) is False


# ---------- 拖动 / 长按 ----------

def test_inject_drag_moves_stepwise_then_releases(monkeypatch):
    """拖动必须「按住 → 逐步移动 → 松开」：瞬移式拖拽触发不了 Unity 的滚动。"""
    moves, flags = [], []
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)
    _stub_user32(monkeypatch, moves)
    _stub_send_events(monkeypatch, flags)

    assert common.inject_drag(0, 0, 100, 0, steps=5) is True
    assert moves[0] == (0, 0), "先瞬移到起点"
    assert moves[-1] == (100, 0), "最后一步必须到终点"
    assert len(moves) == 6, "起点 + 5 个中间步"
    assert flags[0] == (common.MOUSEEVENTF_LEFTDOWN,)
    assert flags[-1] == (common.MOUSEEVENTF_LEFTUP,)


def test_inject_drag_releases_left_button_on_exception(monkeypatch):
    """中途出错也必须松开左键——否则用户所有窗口都会被「拖着」。"""
    flags = []
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)
    _stub_user32(monkeypatch, [], fail_after=3)
    _stub_send_events(monkeypatch, flags)

    with pytest.raises(OSError):
        common.inject_drag(0, 0, 100, 0, steps=5)

    assert flags[-1] == (common.MOUSEEVENTF_LEFTUP,), "异常路径同样要抬起左键"


def test_inject_long_press_holds_at_start(monkeypatch):
    """hold_ms 走原地长按：不移动，按住时长按毫秒累积。"""
    moves, flags = [], []
    slept = []
    monkeypatch.setattr(common.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(common, "check_stop", lambda: None)
    _stub_user32(monkeypatch, moves)
    _stub_send_events(monkeypatch, flags)

    assert common.inject_drag(10, 20, 999, 999, hold_ms=1000) is True
    assert moves == [(10, 20)], "长按不应移动光标"
    assert sum(slept) >= 0.95, "必须真的按住接近 1 秒"
    assert flags[-1] == (common.MOUSEEVENTF_LEFTUP,)


def test_drag_scroll_delegates_to_inject_drag(monkeypatch):
    """滚动复用同一套注入实现，不再自己抄一份 ctypes 结构。"""
    calls = []
    monkeypatch.setattr(common, "inject_drag",
                        lambda *a, **k: calls.append((a, k)) or True)

    assert common._drag_scroll(1, 2, 3, 4, steps=7, step_sleep=0.01) is True
    assert calls == [((1, 2, 3, 4), {"steps": 7, "step_sleep": 0.01})]


# ---------- 调用方接入 ----------

def test_drag_helpers_delegate_to_inject_drag(monkeypatch):
    """drag_utils / warehouse 的 send_drag 都必须走进程内注入（不再写坐标文件）。"""
    calls = []
    monkeypatch.setattr(common, "ensure_game_clickable", lambda: True)
    monkeypatch.setattr(common, "inject_drag",
                        lambda *a, **k: calls.append((a, k)) or True)
    monkeypatch.setattr(warehouse, "inject_drag",
                        lambda *a, **k: calls.append((a, k)) or True)

    assert drag_utils.send_drag(1, 2, 3, 4, hold_ms=4000) is True
    assert warehouse.send_drag(5, 6, 7, 8) is True
    assert calls == [
        ((1, 2, 3, 4), {"hold_ms": 4000}),
        ((5, 6, 7, 8), {}),
    ]


def test_no_module_keeps_coord_ipc_path():
    """坐标 IPC 路径必须彻底消失，否则迟早有人再往那个文件里写。"""
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in ("common.py", "drag_utils.py", "warehouse.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert "coord_path =" not in source, f"{name} 仍在定义坐标文件路径"
        assert "DRAG_COORD_PATH" not in source, f"{name} 仍在定义拖动指令文件路径"
