"""点击链路的守护逻辑测试：注入失败的告警、客户区限定匹配的坐标换算。

这两块都不依赖真实游戏窗口：
- 注入失败告警把 `_write_coord_raw` 打桩成失败，断言 send_coord 当场记日志；
- 区域限定匹配用合成图片与合成模板，验证命中位置与偏移补偿。

（2026-11-17 点击改进程内 SendInput 后，本文件原有的「注入器存活探测」「坐标文件
未消费」两组用例随机制一起删除：没有中间进程，就没有可探测的进程和可残留的坐标文件。）
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common


def test_send_coord_warns_when_injection_fails(monkeypatch):
    """SendInput 失败要当场记日志，而不是静默继续（那会变成「界面 8 轮无变化」）。"""
    messages = []
    monkeypatch.setattr(common, "log", lambda m: messages.append(m))
    monkeypatch.setattr(common, "_restore_cursor", {"enabled": False})
    monkeypatch.setattr(common, "check_stop", lambda: None)
    monkeypatch.setattr(common, "ensure_game_clickable", lambda: True)
    monkeypatch.setattr(common, "point_owned_by_game", lambda *_a: True)
    monkeypatch.setattr(common, "_write_coord_raw", lambda *_a, **_k: False)

    common.send_coord(10, 20)
    assert any("注入失败" in m for m in messages), messages


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
