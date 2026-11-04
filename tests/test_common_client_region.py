"""客户区相对搜索区域：换算（_resolve_search_region）与 find_center / find_center_silent /
wait_and_click 的透传与坐标补偿。

截图、窗口客户区、模板读取与 matchTemplate 全部打桩，不接触真实截屏或游戏窗口。
"""
import os

import numpy as np
import pytest

import common

TEMPLATE = np.zeros((4, 4, 3), dtype=np.uint8)
SCREEN = np.zeros((900, 1600, 3), dtype=np.uint8)
CLIENT_REGION = (10, 20, 50, 30)


class _Clock:
    """可控时钟：记录 sleep 参数并推进 now。"""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _install_stubs(monkeypatch, regions, results):
    """按调用顺序返回窗口矩形与匹配矩阵，并统计两类调用次数。"""
    state = {"region": 0, "match": 0}

    def fake_game_client_region(refresh=False):
        index = min(state["region"], len(regions) - 1)
        state["region"] += 1
        return regions[index]

    def fake_match_template(_image, _template, _method):
        index = min(state["match"], len(results) - 1)
        state["match"] += 1
        return results[index]

    monkeypatch.setattr(common, "game_client_region", fake_game_client_region)
    monkeypatch.setattr(common.cv2, "matchTemplate", fake_match_template)
    monkeypatch.setattr(common, "load_template", lambda _path: TEMPLATE)
    monkeypatch.setattr(common, "get_cached_screenshot", lambda: SCREEN)
    return state


def test_region_and_client_region_are_mutually_exclusive():
    with pytest.raises(ValueError):
        common._resolve_search_region((1, 2, 3, 4), (5, 6, 7, 8))


def test_explicit_region_is_returned_verbatim(monkeypatch):
    monkeypatch.setattr(
        common, "game_client_region",
        lambda *args, **kwargs: pytest.fail("显式 region 不应查询窗口"),
    )
    region = (1, 2, 3, 4)
    assert common._resolve_search_region(region) == region


def test_client_region_is_offset_by_window_origin(monkeypatch):
    monkeypatch.setattr(
        common, "game_client_region", lambda *args, **kwargs: (100, 200, 1600, 900)
    )
    assert common._resolve_search_region(client_region=CLIENT_REGION) == (110, 220, 50, 30)


def test_client_region_without_window_keeps_screen_origin(monkeypatch):
    monkeypatch.setattr(common, "game_client_region", lambda *args, **kwargs: None)
    region = (0, 650, 1600, 250)
    assert common._resolve_search_region(client_region=region) == region


def test_find_center_client_region_hit_is_absolute(monkeypatch):
    """命中坐标 = 客户区原点 + 区域偏移 + 模板半宽高；裁剪确实落在换算后的区域。"""
    result = np.full((27, 47), 0.1, dtype=np.float32)
    result[3, 5] = 0.99
    seen = {}

    def fake_match_template(image, _template, _method):
        seen["shape"] = image.shape
        return result

    monkeypatch.setattr(
        common, "game_client_region", lambda *args, **kwargs: (100, 200, 1600, 900)
    )
    monkeypatch.setattr(common.cv2, "matchTemplate", fake_match_template)
    monkeypatch.setattr(common, "load_template", lambda _path: TEMPLATE)
    monkeypatch.setattr(common, "get_cached_screenshot", lambda: SCREEN)

    assert common.find_center("t.png", client_region=CLIENT_REGION) == (117, 225)
    assert seen["shape"] == (30, 50, 3)


def test_find_center_client_region_below_threshold_returns_none(monkeypatch):
    monkeypatch.setattr(
        common, "game_client_region", lambda *args, **kwargs: (100, 200, 1600, 900)
    )
    monkeypatch.setattr(
        common.cv2, "matchTemplate",
        lambda *args: np.full((27, 47), 0.1, dtype=np.float32),
    )
    monkeypatch.setattr(common, "load_template", lambda _path: TEMPLATE)
    monkeypatch.setattr(common, "get_cached_screenshot", lambda: SCREEN)

    assert common.find_center("t.png", client_region=CLIENT_REGION) is None


def test_find_center_silent_client_region_recomputes_origin_each_round(monkeypatch):
    """窗口被拖动后，第二轮必须按新客户区原点裁剪，且不走「强制刷新」分支。"""
    clock = _Clock()
    monkeypatch.setattr(common, "time", clock)
    regions = [(100, 200, 1600, 900), (120, 220, 1600, 900)]
    results = [
        np.full((5, 5), 0.1, dtype=np.float32),
        np.full((5, 5), 0.1, dtype=np.float32),
    ]
    results[1][0, 0] = 0.99
    state = _install_stubs(monkeypatch, regions, results)

    assert common.find_center_silent(
        "t.png", timeout=0.5, interval=0.25, client_region=(0, 650, 1600, 250)
    ) == (122, 872)
    assert state["region"] == 2
    assert state["match"] == 2
    assert clock.sleeps == [0.25]


def test_find_center_silent_client_region_never_forces_window_refresh(monkeypatch):
    """client_region 每轮都重算客户区，不应再额外查询一次 refresh=True。"""
    clock = _Clock()
    monkeypatch.setattr(common, "time", clock)
    calls = []

    def fake_game_client_region(refresh=False):
        calls.append(refresh)
        return (100, 200, 1600, 900)

    monkeypatch.setattr(common, "game_client_region", fake_game_client_region)
    monkeypatch.setattr(
        common.cv2, "matchTemplate",
        lambda *args: np.full((250, 1600), 0.1, dtype=np.float32),
    )
    monkeypatch.setattr(common, "load_template", lambda _path: TEMPLATE)
    monkeypatch.setattr(common, "get_cached_screenshot", lambda: SCREEN)

    assert common.find_center_silent("t.png", timeout=0, client_region=(0, 650, 1600, 250)) is None
    assert calls == [False]


def test_wait_and_click_forwards_region(monkeypatch):
    seen = {}
    clicks = []

    def fake_find_center(template_path, threshold=0.8, region=None, client_region=None):
        seen.update(template_path=template_path, threshold=threshold,
                    region=region, client_region=client_region)
        return (321, 654)

    monkeypatch.setattr(common, "find_center", fake_find_center)
    monkeypatch.setattr(common, "send_coord", lambda x, y: clicks.append((x, y)))
    monkeypatch.setattr(common, "invalidate_screenshot_cache", lambda: None)

    region = (100, 200, 300, 400)
    assert common.wait_and_click("t.png", "t", region=region) is True
    assert seen["region"] == region
    assert seen["client_region"] is None
    assert clicks == [(321, 654)]


def test_wait_and_click_forwards_client_region(monkeypatch):
    seen = {}
    clicks = []

    def fake_find_center(template_path, threshold=0.8, region=None, client_region=None):
        seen.update(template_path=template_path, threshold=threshold,
                    region=region, client_region=client_region)
        return (500, 700)

    monkeypatch.setattr(common, "find_center", fake_find_center)
    monkeypatch.setattr(common, "send_coord", lambda x, y: clicks.append((x, y)))
    monkeypatch.setattr(common, "invalidate_screenshot_cache", lambda: None)

    client_region = common.BOTTOM_BAR_CLIENT_REGION
    assert common.wait_and_click("t.png", "t", client_region=client_region) is True
    assert seen["region"] is None
    assert seen["client_region"] == client_region
    assert clicks == [(500, 700)]


def test_find_center_silent_legacy_call_keeps_default_behavior(monkeypatch):
    """不传区域的旧调用仍默认整客户区搜索，并在超时=0 时只匹配一次。"""
    clock = _Clock()
    monkeypatch.setattr(common, "time", clock)
    calls = []

    def fake_game_client_region(refresh=False):
        calls.append(refresh)
        return (0, 0, 1600, 900)

    match_count = []

    def fake_match_template(_image, _template, _method):
        match_count.append(1)
        return np.zeros((10, 10), dtype=np.float32)

    monkeypatch.setattr(common, "game_client_region", fake_game_client_region)
    monkeypatch.setattr(common.cv2, "matchTemplate", fake_match_template)
    monkeypatch.setattr(common, "load_template", lambda _path: TEMPLATE)
    monkeypatch.setattr(common, "get_cached_screenshot", lambda: SCREEN)

    assert common.find_center_silent("t.png", timeout=0) is None
    assert calls == [False, True]
    assert len(match_count) == 1


def test_at_main_interface_back_arrow_stays_outside_bottom_band(monkeypatch):
    """返回箭头在底带之外也必须被看到：否则子页会被误判成主界面。"""
    band = common.BOTTOM_BAR_CLIENT_REGION

    def fake_find_center_silent(template_path, threshold=0.8, region=None,
                                timeout=0, interval=0.5, client_region=None):
        name = os.path.basename(template_path)
        if name == "wanfamulu.png":
            return (800, 780) if client_region == band else None
        if name == "exitck.png":
            # 顶部返回箭头不在底部导航带内：限定带内会漏判
            return None if client_region else (50, 100)
        return None

    monkeypatch.setattr(common, "find_center_silent", fake_find_center_silent)

    assert common.at_main_interface() is False

