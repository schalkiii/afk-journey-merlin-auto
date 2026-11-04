"""find_center_silent 未命中路径：双匹配消除与超时/间隔语义。

截图、窗口区域、模板读取与 matchTemplate 全部打桩，不接触真实截屏或游戏窗口。
"""
import numpy as np
import pytest

import common

TEMPLATE = np.zeros((4, 4, 3), dtype=np.uint8)
SCREEN = np.zeros((200, 300, 3), dtype=np.uint8)


class _Clock:
    """可控时钟：记录 sleep 参数并推进 now，用于校验 deadline 截断。"""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _install_stubs(monkeypatch, regions, match_results):
    """按调用顺序返回窗口矩形与匹配矩阵，并统计两类调用次数。"""
    state = {"region": 0, "match": 0}

    def fake_game_client_region(refresh=False):
        index = min(state["region"], len(regions) - 1)
        state["region"] += 1
        return regions[index]

    def fake_match_template(image, template, method):
        index = min(state["match"], len(match_results) - 1)
        state["match"] += 1
        return match_results[index]

    monkeypatch.setattr(common, "game_client_region", fake_game_client_region)
    monkeypatch.setattr(common.cv2, "matchTemplate", fake_match_template)
    monkeypatch.setattr(common, "load_template", lambda _path: TEMPLATE)
    monkeypatch.setattr(common, "get_cached_screenshot", lambda: SCREEN)
    return state


def test_unchanged_rect_matches_only_once(monkeypatch):
    """rect 未变化时不得为一次 miss 做第二次匹配（也不重复截图）。"""
    monkeypatch.setattr(common, "time", _Clock())
    state = _install_stubs(
        monkeypatch,
        regions=[(0, 0, 1600, 900), (0, 0, 1600, 900)],
        match_results=[np.zeros((10, 10))],
    )

    assert common.find_center_silent("t.png", timeout=0) is None
    assert state["match"] == 1
    assert state["region"] == 2


def test_changed_rect_triggers_second_match(monkeypatch):
    """窗口被拖动（rect 变化）时必须重新匹配一次。"""
    monkeypatch.setattr(common, "time", _Clock())
    state = _install_stubs(
        monkeypatch,
        regions=[(10, 10, 400, 300), (20, 20, 400, 300)],
        match_results=[np.zeros((10, 10))],
    )

    assert common.find_center_silent("t.png", timeout=0) is None
    assert state["match"] == 2
    assert state["region"] == 2


def test_sleep_is_clamped_to_remaining_timeout(monkeypatch):
    """timeout 小于 interval 时只能睡剩余时间，不能睡过 deadline。"""
    clock = _Clock()
    monkeypatch.setattr(common, "time", clock)
    _install_stubs(
        monkeypatch,
        regions=[(0, 0, 1600, 900), (0, 0, 1600, 900)],
        match_results=[np.zeros((10, 10))],
    )

    assert common.find_center_silent("t.png", timeout=0.25, interval=0.5) is None
    assert clock.sleeps == [0.25]
    assert clock.now == pytest.approx(0.25)


def test_explicit_region_does_not_refresh_window(monkeypatch):
    """显式 region 时保持旧行为：不查询/刷新窗口矩形。"""
    region = (100, 50, 40, 20)
    calls = []

    def fake_game_client_region(refresh=False):
        calls.append(refresh)
        return region

    monkeypatch.setattr(common, "game_client_region", fake_game_client_region)
    monkeypatch.setattr(common.cv2, "matchTemplate", lambda *args: np.zeros((17, 37)))
    monkeypatch.setattr(common, "load_template", lambda _path: TEMPLATE)
    monkeypatch.setattr(common, "get_cached_screenshot", lambda: SCREEN)

    assert common.find_center_silent("t.png", region=region, timeout=0) is None
    assert calls == []


def test_hit_returns_absolute_center(monkeypatch):
    """命中坐标 = 匹配位置 + 模板半宽高 + region 偏移，保持原语义。"""
    region = (100, 50, 40, 20)
    result = np.full((17, 37), 0.1, dtype=np.float32)
    result[2, 3] = 0.99

    monkeypatch.setattr(common, "game_client_region", lambda refresh=False: region)
    monkeypatch.setattr(common.cv2, "matchTemplate", lambda *args: result)
    monkeypatch.setattr(common, "load_template", lambda _path: TEMPLATE)
    monkeypatch.setattr(common, "get_cached_screenshot", lambda: SCREEN)

    assert common.find_center_silent("t.png", region=region) == (105, 54)
