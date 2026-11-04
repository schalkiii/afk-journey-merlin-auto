"""common 区域变化原语：比较（crops_differ）与轮询等待（region_changed_since）。

不接触真实截屏：截图与客户区都打桩，用 numpy 合成图。比较只看两帧裁剪，
等待建立在比较之上并每轮取新帧——缓存帧在 0.4s 级轮询里永远看不到变化。
"""
import numpy as np
import pytest

import common

REGION = (100, 50, 40, 20)


class _Clock:
    """可控时钟：region_changed_since 同时用到 time.time 与 time.sleep。"""

    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _noise_frame(seed=0, size=(900, 1600, 3)):
    rng = np.random.RandomState(seed)
    return rng.randint(0, 256, size=size, dtype=np.uint8)


def _crop(frame, region=REGION, origin=(0, 0), shift=0):
    origin_x, origin_y = origin
    x, y, w, h = region
    return frame[origin_y + y:origin_y + y + h,
                 origin_x + x + shift:origin_x + x + shift + w]


def _stub_capture(monkeypatch, frames, origin=(0, 0)):
    """桩掉截图与客户区；frames 为逐轮返回的帧，越界后沿用最后一帧。"""
    calls = {"count": 0}

    def fake_screenshot():
        index = min(calls["count"], len(frames) - 1)
        calls["count"] += 1
        return frames[index]

    monkeypatch.setattr(common, "screenshot_bgr", fake_screenshot)
    monkeypatch.setattr(
        common, "game_client_region", lambda: (origin[0], origin[1], 1600, 900)
    )
    return calls


def test_crops_differ_false_for_identical_crop():
    frame = _noise_frame()
    crop = _crop(frame)
    assert common.crops_differ(crop, crop.copy(), 0.97) is False


def test_crops_differ_true_when_content_shifted_by_one_pixel():
    frame = _noise_frame(seed=1)
    before = _crop(frame)
    after = _crop(np.roll(frame, 1, axis=1))
    assert common.crops_differ(before, after, 0.97) is True


def test_crops_differ_false_when_shapes_differ():
    """形状不一致视为未变化（与红点领取的既有语义一致），不得判成功。"""
    before = np.zeros((20, 40, 3), dtype=np.uint8)
    after = np.zeros((21, 40, 3), dtype=np.uint8)
    assert common.crops_differ(before, after, 0.5) is False


def test_crops_differ_at_exact_threshold_is_unchanged():
    """分数恰等于阈值时算未变化（判据是严格小于）。"""
    frame = _noise_frame(seed=2)
    before = _crop(frame)
    after = _crop(frame, shift=2)
    score = float(
        common.cv2.matchTemplate(after, before, common.cv2.TM_CCOEFF_NORMED).max()
    )
    assert common.crops_differ(before, after, score) is False


def test_region_changed_since_true_when_region_content_shifts(monkeypatch):
    frame = _noise_frame(seed=3)
    shifted = np.roll(frame, 1, axis=1)
    clock = _Clock()
    monkeypatch.setattr(common, "time", clock)
    _stub_capture(monkeypatch, [frame, shifted])

    assert common.region_changed_since(
        _crop(frame), REGION, threshold=0.97, timeout=0.8
    ) is True


def test_region_changed_since_false_when_unchanged_until_timeout(monkeypatch):
    frame = _noise_frame(seed=4)
    clock = _Clock()
    monkeypatch.setattr(common, "time", clock)
    calls = _stub_capture(monkeypatch, [frame])
    monkeypatch.setattr(
        common, "get_cached_screenshot", lambda: pytest.fail("轮询必须取新帧，不能读缓存帧")
    )

    assert common.region_changed_since(
        _crop(frame), REGION, threshold=0.97, timeout=0.8
    ) is False
    assert calls["count"] >= 2, "超时前必须真的轮询过，而不是只看一帧"


def test_region_changed_since_timeout_zero_still_checks_once(monkeypatch):
    """timeout=0 也要先确认一次，与仓库 _wait_gone 的既有语义一致。"""
    frame = _noise_frame(seed=5)
    monkeypatch.setattr(common, "time", _Clock())
    calls = _stub_capture(monkeypatch, [frame])

    assert common.region_changed_since(
        _crop(frame), REGION, threshold=0.97, timeout=0.0
    ) is False
    assert calls["count"] == 1


def test_region_changed_since_crops_from_client_origin(monkeypatch):
    """裁剪必须按客户区原点偏移；原点之外的改动不能算作区域内变化。"""
    frame = _noise_frame(seed=6)
    origin = (200, 100)
    changed = frame.copy()
    changed[origin[1]:origin[1] + 30, origin[0]:origin[0] + 60] = 255
    monkeypatch.setattr(common, "time", _Clock())
    _stub_capture(monkeypatch, [changed], origin=origin)

    assert common.region_changed_since(
        _crop(frame, origin=origin), REGION, threshold=0.97, timeout=0.8
    ) is False


def test_region_changed_since_propagates_stop_request(monkeypatch):
    """check_stop 的 StopRequested/异常必须透传，不能被轮询吞掉。"""
    frame = _noise_frame(seed=7)
    monkeypatch.setattr(common, "time", _Clock())
    _stub_capture(monkeypatch, [frame])

    def raise_stop():
        raise RuntimeError("F9 停止")

    monkeypatch.setattr(common, "check_stop", raise_stop)
    with pytest.raises(RuntimeError):
        common.region_changed_since(_crop(frame), REGION, threshold=0.97, timeout=0.8)
