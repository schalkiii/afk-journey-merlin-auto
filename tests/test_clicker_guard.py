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


def test_clear_stale_coord_removes_ipc_file(isolated_coord):
    """兼容符号 clear_stale_coord 仍清掉旧版残留坐标，避免误点。"""
    with open(isolated_coord, "w", encoding="utf-8") as handle:
        handle.write("100 200")
    assert common.clear_stale_coord() is True
    assert not os.path.exists(isolated_coord)
    assert common.clear_stale_coord() is False


def test_clicker_alive_does_not_write_coord(isolated_coord, monkeypatch):
    """负验证：clicker_alive 恒 True 且绝不产生点击副作用（不写坐标文件）。"""
    monkeypatch.setattr(common.subprocess, "run", _fake_tasklist(b""))
    assert common.clicker_alive() is True
    assert not os.path.exists(isolated_coord), "就绪探测绝不能写坐标 IPC 文件"


def test_clicker_alive_independent_of_process_list(isolated_coord, monkeypatch):
    """2026-11-17 起进程内注入：无论 tasklist 报有/无进程，就绪判定都不变。"""
    mono = _fake_tasklist("INFO: No tasks are running which match the specified criteria.")
    monkeypatch.setattr(common.subprocess, "run", mono)
    assert common.clicker_alive() is True

    def boom(*_args, **_kwargs):
        raise subprocess.SubprocessError("tasklist unavailable")

    monkeypatch.setattr(common.subprocess, "run", boom)
    assert common.clicker_alive() is True, "进程内注入不依赖任何外部进程探测"


def test_send_coord_warns_when_injection_fails(isolated_coord, monkeypatch):
    """2026-11-17 进程内注入：SendInput 失败要记日志（不再抛 ClickerNotRunning）。

    旧实现靠「坐标无人消费」判定注入器退出并抛 ClickerNotRunning；进程内方案没有
    中间进程和坐标文件，失败模式变成 inject_click 返回 False，故改为记告警。
    """
    messages = []
    monkeypatch.setattr(common, "log", lambda m: messages.append(m))
    monkeypatch.setattr(common, "_restore_cursor", {"enabled": False})
    monkeypatch.setattr(common, "check_stop", lambda: None)
    monkeypatch.setattr(common, "ensure_game_clickable", lambda: True)
    monkeypatch.setattr(common, "point_owned_by_game", lambda *_a: True)
    monkeypatch.setattr(common, "_write_coord_raw", lambda *_a, **_k: False)

    common.send_coord(10, 20)
    assert any("注入失败" in m for m in messages), messages


def test_clicker_alive_always_true_for_in_process_injection(isolated_coord, monkeypatch):
    """进程内注入没有外部进程可探测；clicker_alive 恒 True（兼容旧调用点）。

    负验证：若把它改回 tasklist 探测，无进程时会返回 False，本用例变红。
    """
    monkeypatch.setattr(common.subprocess, "run",
                        _fake_tasklist("INFO: No tasks are running which match the specified criteria."))
    with open(isolated_coord, "w", encoding="utf-8") as handle:
        handle.write("100 200")
    assert common.clicker_alive() is True


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
