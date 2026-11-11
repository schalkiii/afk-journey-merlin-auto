"""点击链路的守护逻辑测试：点击器存活探测、坐标未消费告警、客户区限定匹配的坐标换算。

这三个功能都不依赖真实游戏窗口：
- 存活探测打桩 `subprocess.run`，并断言探测过程不写坐标文件（不得产生真实点击）；
- 未消费告警用临时目录里的假坐标文件模拟「无人消费」；
- 区域限定匹配用合成图片与合成模板，验证命中位置与偏移补偿。
"""
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common


@pytest.fixture
def isolated_coord(tmp_path, monkeypatch):
    """把坐标文件指向临时目录，避免污染真实的 shared/target_coord.txt。"""
    path = str(tmp_path / "target_coord.txt")
    monkeypatch.setattr(common, "coord_path", path)
    monkeypatch.setattr(common, "_clicker_miss", {"streak": 0})
    return path


def _fake_tasklist(stdout):
    """tasklist 以 bytes 返回（中文 Windows 上 stdout 是 GBK，不能按 text 解析）。"""
    return lambda *_args, **_kwargs: subprocess.CompletedProcess(
        args=["tasklist"], returncode=0,
        stdout=stdout if isinstance(stdout, bytes) else stdout.encode("ascii"),
        stderr=b"",
    )


def test_clicker_alive_false_when_coord_never_consumed(isolated_coord, monkeypatch):
    """坐标文件残留时直接判死，且不产生任何新的点击副作用。"""
    with open(isolated_coord, "w", encoding="utf-8") as handle:
        handle.write("100 200")
    monkeypatch.setattr(common.subprocess, "run", _fake_tasklist("click_from_file.exe"))
    assert common.clicker_alive() is False
    assert os.path.exists(isolated_coord), "残留坐标文件应由调用方处理，探测不得改动它"


def test_clicker_alive_reads_process_list_without_writing_coord(isolated_coord, monkeypatch):
    """负验证：把探测改回「写哨兵坐标」，本用例会因文件被创建而失败。"""
    monkeypatch.setattr(common.subprocess, "run",
                        _fake_tasklist("click_from_file.exe   1234 Console   1   10,000 K"))
    assert common.clicker_alive() is True
    assert not os.path.exists(isolated_coord), "只读探测绝不能写坐标 IPC 文件"


def test_clicker_alive_false_when_process_absent(isolated_coord, monkeypatch):
    monkeypatch.setattr(common.subprocess, "run",
                        _fake_tasklist("INFO: No tasks are running which match the specified criteria."))
    assert common.clicker_alive() is False


def test_clicker_alive_assumes_alive_when_probe_fails(isolated_coord, monkeypatch):
    """探测失败时按存活处理，交给 send_coord 的连续未消费计数兜底。"""
    def boom(*_args, **_kwargs):
        raise subprocess.SubprocessError("tasklist unavailable")

    monkeypatch.setattr(common.subprocess, "run", boom)
    assert common.clicker_alive() is True


def test_clicker_alive_tolerates_gbk_output(isolated_coord, monkeypatch):
    """中文 Windows 的 tasklist 输出是 GBK：按 bytes 解析，不能因解码错误崩溃。

    2026-11-08 实机踩过：`text=True` 用 UTF-8 解 GBK 抛 UnicodeDecodeError、
    stdout 变 None，`in None` 直接 TypeError。
    """
    gbk = "信息: 没有运行的任务匹配指定标准。\n".encode("gbk")
    monkeypatch.setattr(common.subprocess, "run", _fake_tasklist(gbk))
    assert common.clicker_alive() is False


def test_send_coord_raises_after_consecutive_misses(isolated_coord):
    for _ in range(common.CLICKER_MISS_LIMIT - 1):
        common.send_coord(10, 20)
    with pytest.raises(common.ClickerNotRunning):
        common.send_coord(10, 20)


def test_send_coord_resets_streak_when_consumed(isolated_coord, monkeypatch):
    """被正常消费时不应累计漏消费次数，更不应抛错。"""
    real_wait = common.time.sleep

    def consume_then_sleep(seconds):
        # send_coord 写入后会在轮询中检查文件是否存在；这里在首次轮询前删掉它，模拟被读走
        if os.path.exists(isolated_coord):
            os.remove(isolated_coord)
        real_wait(0)

    monkeypatch.setattr(common.time, "sleep", consume_then_sleep)
    for _ in range(common.CLICKER_MISS_LIMIT + 2):
        common.send_coord(10, 20)
    assert common._clicker_miss["streak"] == 0


def _textured_marker(height=20, width=30):
    """构造有纹理的模板。

    纯色块不能用作 TM_CCOEFF_NORMED 的模板：该归一化会去掉均值，导致纯色模板与任意
    纯色区域相关系数都接近 1，从而在"区域外"也误报命中。真实游戏 UI 都有纹理，
    测试素材同理需要纹理才能反映真实判定行为。
    """
    marker = np.zeros((height, width, 3), dtype=np.uint8)
    for row in range(height):
        for col in range(width):
            marker[row, col] = (
                (row * 11 + col * 7) % 256,
                (row * 5 + col * 13) % 256,
                (row * 17 + col * 3) % 256,
            )
    return marker


def test_region_limited_match_returns_absolute_coordinates(monkeypatch):
    """限定搜索区域后，返回值必须换算回全屏绝对坐标，与原全屏匹配一致。"""
    marker = _textured_marker()
    screen = np.zeros((300, 500, 3), dtype=np.uint8)
    # 把标记画在 (x=260, y=150)，模拟游戏窗口内的一个按钮
    screen[150:170, 260:290] = marker

    monkeypatch.setattr(common, "load_template", lambda _path: marker)
    monkeypatch.setattr(common, "get_cached_screenshot", lambda: screen)

    expected = (260 + 30 // 2, 150 + 20 // 2)

    # 区域覆盖标记所在位置
    assert common.find_center_silent("ignored.png", 0.9, region=(200, 100, 300, 200)) == expected
    # 全屏匹配（region 显式给整屏）结果必须一致
    assert common.find_center_silent("ignored.png", 0.9, region=(0, 0, 500, 300)) == expected


def test_region_limited_match_misses_outside_region(monkeypatch):
    marker = _textured_marker()
    screen = np.zeros((300, 500, 3), dtype=np.uint8)
    screen[150:170, 260:290] = marker

    monkeypatch.setattr(common, "load_template", lambda _path: marker)
    monkeypatch.setattr(common, "get_cached_screenshot", lambda: screen)

    # 区域不覆盖标记 -> 必须返回 None，而不是把区域外的目标误报成命中
    assert common.find_center_silent("ignored.png", 0.9, region=(0, 0, 200, 100)) is None


def test_game_client_region_shape():
    region = common.game_client_region(refresh=True)
    assert region is None or (
        isinstance(region, tuple) and len(region) == 4 and all(v > 0 for v in region[2:])
    ), "客户区应为 (x, y, w, h) 四元组且宽高为正，或 None 表示回退全屏"
