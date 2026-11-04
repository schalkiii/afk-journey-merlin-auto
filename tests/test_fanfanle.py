"""翻翻乐模块：烧钥匙循环的计数与停止条件（不接触真实游戏）。

关键性质：一次点击会连抽到本轮 100 满，所以「钥匙余量有没有变」是唯一的成败判据——
判据错了就会像最初那样把「已经推进」误读成「点了没反应」。
"""
import fanfanle as ff


def _patch_common(monkeypatch, button_pos=(1000, 750)):
    clicks = []
    monkeypatch.setattr(ff, "check_stop", lambda: None)
    monkeypatch.setattr(ff, "invalidate_screenshot_cache", lambda: None)
    monkeypatch.setattr(ff, "find_center_silent", lambda *args, **kwargs: button_pos)
    monkeypatch.setattr(ff, "click_position", lambda pos, **kwargs: clicks.append(pos))
    monkeypatch.setattr(ff, "_keys_region_crop", lambda: b"crop")
    return clicks


def test_burn_stops_when_keys_unchanged(monkeypatch):
    """钥匙余量不变＝没钥匙了，必须停，不能对着按钮空转。"""
    clicks = _patch_common(monkeypatch)
    monkeypatch.setattr(ff, "_wait_keys_change", lambda before, timeout=3.0: False)

    assert ff.burn_keys(5) == 0
    assert len(clicks) == 1, "只应试一次就停"


def test_burn_counts_every_round_that_consumes_keys(monkeypatch):
    """前两轮钥匙被烧掉要计数，第三轮烧完（余量不变）停止。"""
    changes = iter([True, True, False])
    _patch_common(monkeypatch)
    monkeypatch.setattr(ff, "_wait_keys_change", lambda before, timeout=3.0: next(changes))

    assert ff.burn_keys(10) == 2


def test_burn_stops_when_button_disappears(monkeypatch):
    """按钮消失（界面被弹窗顶掉等）时结束，不拿 None 坐标去点。"""
    monkeypatch.setattr(ff, "check_stop", lambda: None)
    monkeypatch.setattr(ff, "invalidate_screenshot_cache", lambda: None)
    monkeypatch.setattr(ff, "_keys_region_crop", lambda: b"crop")
    monkeypatch.setattr(ff, "_wait_keys_change", lambda before, timeout=3.0: True)
    positions = iter([(1000, 750), None])
    clicks = []
    monkeypatch.setattr(ff, "find_center_silent", lambda *args, **kwargs: next(positions))
    monkeypatch.setattr(ff, "click_position", lambda pos, **kwargs: clicks.append(pos))

    assert ff.burn_keys(10) == 1
    assert clicks == [(1000, 750)]


def test_burn_uses_single_click_not_double(monkeypatch):
    """连点两下会白烧一整轮钥匙，必须 twice=False。"""
    seen = {}
    _patch_common(monkeypatch)
    monkeypatch.setattr(ff, "_wait_keys_change", lambda before, timeout=3.0: False)

    def fake_click(pos, wait=1.5, twice=True):
        seen["twice"] = twice

    monkeypatch.setattr(ff, "click_position", fake_click)
    ff.burn_keys(1)
    assert seen.get("twice") is False


def test_main_caps_rounds_before_burning(monkeypatch):
    """轮数上限要夹住，防止配置里写进一个离谱值把钥匙一次烧光。"""
    asked = []
    monkeypatch.setattr(ff, "recover_to_main_interface", lambda: True)
    monkeypatch.setattr(ff, "_enter_fanfanle", lambda: True)
    monkeypatch.setattr(ff, "log", lambda *args, **kwargs: None)

    def fake_burn(max_rounds):
        asked.append(max_rounds)
        return 0

    monkeypatch.setattr(ff, "burn_keys", fake_burn)
    assert ff.main(max_rounds=9999) is True
    assert asked == [ff.MAX_ROUNDS_LIMIT]
