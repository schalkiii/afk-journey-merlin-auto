"""2026-11-17：点击注入从「AHK 独立进程 + txt 坐标」改为「进程内 SendInput」。

负验证留痕（把对应实现改回去，下列用例必须变红）：
- `inject_click` 改用 mouse_event 分离 DOWN/UP + sleep →
  `test_inject_click_uses_sendinput_atomically` 必须失败；
- `send_coord` 改回写坐标文件 → `test_send_coord_does_not_touch_coord_file` 必须失败；
- `clicker_alive` 改回 tasklist 探测 → `test_clicker_helpers_are_in_process` 必须失败。
"""
import common


class _FakeInputArray:
    """足够 _send_mouse_events 用的 ctypes 数组替身，记录 SendInput 收到的事件。"""

    def __init__(self, count):
        self.items = [type("Evt", (), {"mi": None})() for _ in range(count)]

    def __setitem__(self, index, value):
        self.items[index] = value


def test_inject_click_uses_sendinput_atomically(monkeypatch):
    """DOWN/UP 必须在同一次 SendInput 调用里提交，避免中断卡住左键。"""
    calls = []
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)

    def fake_set_cursor(x, y):
        calls.append(("move", x, y))

    class _User32:
        def SetCursorPos(self, x, y):
            fake_set_cursor(x, y)

    monkeypatch.setattr(common.ctypes, "windll", type("W", (), {"user32": _User32()}))

    def fake_send(*flags):
        # 传入的是鼠标事件 flag 列表，必须为 2 个（DOWN + UP）原子提交
        calls.append(("sendinput", len(flags)))
        return len(flags)  # 全部注入成功

    monkeypatch.setattr(common, "_send_mouse_events", fake_send)

    assert common.inject_click(123, 456) is True
    assert calls[0] == ("move", 123, 456)
    assert calls[1][0] == "sendinput"
    assert calls[1][1] == 2, "按下+松开必须一次原子提交，不能分离成两次调用"


def test_inject_click_reports_failure(monkeypatch):
    """SendInput 返回的事件数不足时要报失败，让 send_coord 记告警。"""
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)

    class _User32:
        def SetCursorPos(self, _x, _y):
            pass

    monkeypatch.setattr(common.ctypes, "windll", type("W", (), {"user32": _User32()}))
    monkeypatch.setattr(common, "_send_mouse_events", lambda *_a: 0)
    assert common.inject_click(1, 2) is False


def test_send_coord_does_not_touch_coord_file(tmp_path, monkeypatch):
    """send_coord 绝不能写坐标文件——这是去掉 AHK 中间层的核心验收点。"""
    coord = tmp_path / "target_coord.txt"
    monkeypatch.setattr(common, "coord_path", str(coord))
    monkeypatch.setattr(common, "_restore_cursor", {"enabled": False})
    monkeypatch.setattr(common, "check_stop", lambda: None)
    monkeypatch.setattr(common, "ensure_game_clickable", lambda: True)
    monkeypatch.setattr(common, "point_owned_by_game", lambda *_a: True)
    monkeypatch.setattr(common, "_write_coord_raw", lambda *_a, **_k: True)

    common.send_coord(700, 800)
    assert not coord.exists(), "进程内注入不应创建任何坐标 IPC 文件"


def test_clicker_helpers_are_in_process(tmp_path, monkeypatch):
    """clicker_alive / clicker_process_alive 恒 True：没有外部进程可探测。"""
    coord = tmp_path / "target_coord.txt"
    coord.write_text("999 999", encoding="utf-8")
    monkeypatch.setattr(common, "coord_path", str(coord))
    assert common.clicker_alive() is True
    assert common.clicker_process_alive() is True


def test_clicker_not_running_is_compatible_symbol():
    """ClickerNotRunning 保留为兼容符号，仍是 RuntimeError 子类。"""
    assert issubclass(common.ClickerNotRunning, RuntimeError)
