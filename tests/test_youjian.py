"""邮件面板轮询：加载慢时单次立即判定会把面板误判成「没按钮」（不接触真实游戏）。

今日日志证据：`youjian` 连续 19 次未命中、6.6 秒才命中；随后面板按钮若只查一次，
在加载/动画期同样会漏判，因此改为限时轮询。
"""
import types

import youjian as yj

READ_POS = (120, 240)
UNREAD_POS = (360, 480)


class _FakeClock:
    """假时钟：每次 time() 推进 step 秒，sleep 只记账不真等（测试绝不挂住）。"""

    def __init__(self, step=0.5):
        self.now = 0.0
        self.step = step
        self.slept = []

    def time(self):
        value = self.now
        self.now += self.step
        return value

    def sleep(self, seconds):
        self.slept.append(seconds)


def _patch_clock(monkeypatch, clock):
    monkeypatch.setattr(yj, "time", types.SimpleNamespace(time=clock.time, sleep=clock.sleep))


def test_wait_mail_state_polls_until_read(monkeypatch):
    """前两探 None、第三探命中已读按钮：命中即返回，且后续不再多探。"""
    clock = _FakeClock()
    calls = []

    def fake_find(template_path, threshold=0.8, **kwargs):
        calls.append(template_path)
        return READ_POS if len(calls) == 3 else None

    _patch_clock(monkeypatch, clock)
    monkeypatch.setattr(yj, "find_center", fake_find)

    assert yj._wait_mail_state() == ("read", READ_POS)
    assert calls == [yj.yueduquanbu_path, yj.notyueduquanbu_path, yj.yueduquanbu_path]
    assert clock.slept == [0.5]


def test_wait_mail_state_returns_unread_position(monkeypatch):
    """未读按钮命中时返回 unread 与它自己的坐标，不误用已读按钮的位置。"""
    clock = _FakeClock()
    calls = []

    def fake_find(template_path, threshold=0.8, **kwargs):
        calls.append(template_path)
        return UNREAD_POS if template_path == yj.notyueduquanbu_path else None

    _patch_clock(monkeypatch, clock)
    monkeypatch.setattr(yj, "find_center", fake_find)

    assert yj._wait_mail_state() == ("unread", UNREAD_POS)
    assert calls == [yj.yueduquanbu_path, yj.notyueduquanbu_path]


def test_wait_mail_state_times_out(monkeypatch):
    """窗口内始终没按钮：返回 (None, None)，不会无限轮询。"""
    clock = _FakeClock()
    _patch_clock(monkeypatch, clock)
    monkeypatch.setattr(yj, "find_center", lambda *args, **kwargs: None)

    assert yj._wait_mail_state(timeout=1.0) == (None, None)


def _stub_main(monkeypatch, state):
    """桩掉主流程的点击与面板等待；返回点击名称序列。"""
    clicks = []

    def fake_wait_and_click(template_path, name, *args, **kwargs):
        clicks.append(name)
        return True

    monkeypatch.setattr(yj, "wait_and_click", fake_wait_and_click)
    monkeypatch.setattr(yj, "_wait_mail_state", lambda **kwargs: state)
    _patch_clock(monkeypatch, _FakeClock())
    return clicks


def test_main_read_state_clicks_read_all_then_exits_twice(monkeypatch):
    """read：点一键已读 → 关空白 → 连续两次 exit。"""
    clicks = _stub_main(monkeypatch, ("read", READ_POS))

    assert yj.main() is True
    assert clicks == ["caidan", "youjian", "yueduquanbu", "dianjikongbaichuguanbi",
                      "exit", "exit"]


def test_main_unread_state_skips_read_all_button(monkeypatch):
    """unread：直接走两次 exit，不点一键已读按钮。"""
    clicks = _stub_main(monkeypatch, ("unread", UNREAD_POS))

    assert yj.main() is True
    assert clicks == ["caidan", "youjian", "exit", "exit"]


def test_main_returns_false_when_panel_never_loads(monkeypatch):
    """轮询超时：主流程判失败并终止。"""
    clicks = _stub_main(monkeypatch, (None, None))

    assert yj.main() is False
    assert clicks == ["caidan", "youjian"]
