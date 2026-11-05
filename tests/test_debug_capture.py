"""失败现场逐帧留存的回归测试。

用临时工作目录与小型 numpy 帧验证落盘内容、目录裁剪与开关语义，
不接触真实游戏窗口，也不写项目根目录。
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common


@pytest.fixture
def capture_env(tmp_path, monkeypatch):
    """把工作目录与客户区都隔离到临时环境，并清空环形缓冲。"""
    monkeypatch.setattr(
        common, "get_work_path", lambda relative: str(tmp_path / relative))
    monkeypatch.setattr(
        common, "game_client_region", lambda refresh=False: (10, 10, 40, 40))
    monkeypatch.setattr(common, "DEBUG_CAPTURE_ENABLED", True)
    with common._frame_ring_lock:
        common._frame_ring.clear()
    yield tmp_path
    with common._frame_ring_lock:
        common._frame_ring.clear()


def _push_frames(count):
    """向环形缓冲塞入形状合法、内容可区分的小帧。"""
    for index in range(count):
        frame = np.full((30, 40, 3), index * 40, dtype=np.uint8)
        common._remember_frame(frame)


def test_capture_writes_frames_client_and_meta(capture_env):
    _push_frames(3)

    dest = common.capture_failure_context("测试任务", "任务失败或超时", extra="附加 A")

    assert dest is not None
    destination = os.path.join(capture_env, "debug", "failures")
    assert os.path.isdir(dest) and os.path.dirname(dest) == destination
    for index in range(3):
        assert os.path.exists(os.path.join(dest, f"frame_{index:02d}.jpg"))
    assert os.path.exists(os.path.join(dest, "client.jpg"))
    meta_path = os.path.join(dest, "meta.txt")
    assert os.path.exists(meta_path)
    with open(meta_path, encoding="utf-8") as stream:
        meta = stream.read()
    assert "测试任务" in meta, "meta 必须写明失败任务"
    assert "任务失败或超时" in meta
    assert "附加 A" in meta


def test_capture_keeps_only_latest_five_failure_dirs(capture_env):
    failures_dir = capture_env / "debug" / "failures"
    failures_dir.mkdir(parents=True)
    # 造 7 个更早的现场目录；再加本次现场后应只保留最新 5 个
    for index in range(7):
        (failures_dir / f"20200101-00000{index}_旧_{index}").mkdir()

    _push_frames(1)
    dest = common.capture_failure_context("测试任务", "任务失败或超时")

    remaining = sorted(path.name for path in failures_dir.iterdir() if path.is_dir())
    assert len(remaining) == 5
    assert os.path.basename(dest) in remaining, "最新现场不能被裁掉"
    for stale in range(3):
        assert not (failures_dir / f"20200101-00000{stale}_旧_{stale}").exists()


def test_capture_does_nothing_when_disabled(capture_env, monkeypatch):
    monkeypatch.setattr(common, "DEBUG_CAPTURE_ENABLED", False)
    _push_frames(2)

    dest = common.capture_failure_context("测试任务", "任务失败或超时")

    assert dest is None
    assert not (capture_env / "debug").exists(), "关闭时不得写任何现场文件"
