"""flow_migong（迷梦之役）纯决策逻辑单元测试。

测试环境没有游戏窗口：截图/模板匹配/点击（写坐标文件给 AHK）全部在模块级
接缝（click_template / wait_mg / send_coord / send_drag / cv2.matchTemplate 等）
打桩，只验证状态选择、去重排序、失败清理与次数上限这些决策逻辑。
结构参照 tests/test_push_fail_limit.py（仓库内状态机测试范本）。
"""
import time

import numpy as np
import pytest

import flow_migong


@pytest.fixture
def clean_state(monkeypatch):
    """隔离模块级配置状态并去掉所有真实等待。

    为什么：`cfg` 会读模块全局 `_config`/`_run_params`，用例间必须清零防串扰；
    handle_failure / flow_migong 里有秒级 time.sleep，不桩掉会让单测按秒计时。
    """
    monkeypatch.setattr(flow_migong, "_config", {})
    monkeypatch.setattr(flow_migong, "_run_params", {})
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


# ============================================================
# cfg：运行时参数优先 / 缺 key 回 default / 配置文件缺失
# ============================================================
def test_cfg_prefers_runtime_params_and_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(flow_migong, "_config", {"thresholds": {"default": 0.9}})
    monkeypatch.setattr(flow_migong, "_run_params", {"challenges": 5})

    # GUI 传入的运行时参数必须压过文件配置
    assert flow_migong.cfg("challenges", 3) == 5
    assert flow_migong.cfg("thresholds") == {"default": 0.9}
    # 配置里不存在的 key 返回调用方给的 default，不抛异常
    assert flow_migong.cfg("not_in_config", 42) == 42


def test_cfg_raises_when_config_file_missing(monkeypatch, tmp_path):
    """实测契约：配置文件缺失时 cfg 并不静默返回 default，而是由 load_config 抛出 FileNotFoundError。"""
    monkeypatch.setattr(flow_migong, "_config", None)
    monkeypatch.setattr(flow_migong, "get_config_path",
                        lambda name: str(tmp_path / "missing.json"))
    with pytest.raises(FileNotFoundError):
        flow_migong.cfg("anything", 7)


# ============================================================
# _pick_closest_mgzd：欧氏距离最近 / 空表短路 / 默认路径查一次
# ============================================================
def test_pick_closest_uses_euclidean_distance():
    # (2,2) 欧氏距离≈2.83 < (3,0) 的 3.0；若按曼哈顿距离会选 (3,0)（4 < 6），
    # 因此本断言能区分两种距离判据。
    mgzds = [(2, 2), (3, 0)]
    assert flow_migong._pick_closest_mgzd(0, 0, mgzds) == (2, 2)


def test_pick_closest_empty_list_skips_screen_lookup(monkeypatch):
    """显式传空列表时必须直接返回 None，不得回退去调 find_all_instances_mg 查屏。"""
    calls = []

    def _fake_find(*args, **kwargs):
        calls.append(args)
        return [(9, 9)]

    monkeypatch.setattr(flow_migong, "find_all_instances_mg", _fake_find)
    assert flow_migong._pick_closest_mgzd(500, 500, mgzds=[]) is None
    assert calls == []


def test_pick_closest_default_path_looks_up_once(monkeypatch):
    """不传 mgzds 时应恰好调用一次 find_all_instances_mg 并从中选最近。"""
    calls = []

    def _fake_find(*args, **kwargs):
        calls.append(args)
        return [(1, 1), (10, 10)]

    monkeypatch.setattr(flow_migong, "find_all_instances_mg", _fake_find)
    assert flow_migong._pick_closest_mgzd(9, 9) == (10, 10)
    assert len(calls) == 1


# ============================================================
# find_all_instances_mg：阈值边界 / min_gap 去重 / 按 y 升序
# ============================================================
def _patch_matcher(monkeypatch, res):
    """把匹配结果替换成预置分数图。

    为什么：真机 res 约 1596x896（≈143 万像素），测试只关心决策逻辑，
    用 20x24 量级小图同时避免截图/模板加载与尺寸相关的耗时。
    模板桩成 5x5 → 中心偏移 (2, 2)。
    """
    import cv2

    monkeypatch.setattr(flow_migong, "load_template",
                        lambda path: np.zeros((5, 5, 3), np.uint8))
    monkeypatch.setattr(cv2, "matchTemplate", lambda *args, **kwargs: res)
    return np.zeros((8, 8, 3), np.uint8)  # img 内容无关，matchTemplate 已被桩掉


def test_find_all_instances_threshold_includes_boundary(clean_state, monkeypatch):
    res = np.zeros((20, 20), np.float32)
    res[0, 0] = 0.5   # 恰等于阈值：>= 判定应保留
    res[5, 5] = 0.49  # 低于阈值：应丢弃
    img = _patch_matcher(monkeypatch, res)

    # 显式传 threshold，绕开 cfg；min_gap=6 时两点中心距 (3,3) 不触发去重
    peaks = flow_migong.find_all_instances_mg("x", threshold=0.5, min_gap=6, img=img)
    assert peaks == [(2, 2)]


def test_find_all_instances_min_gap_dedup(clean_state, monkeypatch):
    res = np.zeros((24, 24), np.float32)
    res[0, 0] = 0.9   # 中心 (2, 2)
    res[1, 1] = 0.9   # 中心 (3, 3)：与 (2,2) 的 dx、dy 均 < 6 → 视为同一实例，去掉
    res[0, 6] = 0.9   # 中心 (8, 2)：dx == 6，`<` 判定不算太近 → 保留为独立实例
    img = _patch_matcher(monkeypatch, res)

    peaks = flow_migong.find_all_instances_mg("x", threshold=0.5, min_gap=6, img=img)
    assert peaks == [(2, 2), (8, 2)]


def test_find_all_instances_sorted_by_y_ascending(clean_state, monkeypatch):
    """结果必须按 y 从上到下——调用方 _pick_closest_mgzd 之外还有一处依赖「第一个即最上面一行」。

    诚实标注：当前实现用 np.argwhere 取候选，其行主序在二维 res 上仍按 y 递增，
    所以 `loc.sort` 在这一版里仍是恒等操作，删掉也不会让本例变红。保留本用例
    是为了守住契约：一旦日后换成按分数排序或其它不保序的候选来源，这条排序
    就成了真正承重的防线。
    """
    res = np.zeros((24, 24), np.float32)
    res[4, 10] = 0.9   # 中心 (12, 6)
    res[16, 2] = 0.9   # 中心 (4, 18)：y 更大但 x 更小，排序后应排在 (12,6) 之后
    img = _patch_matcher(monkeypatch, res)

    peaks = flow_migong.find_all_instances_mg("x", threshold=0.5, min_gap=6, img=img)
    assert peaks == [(12, 6), (4, 18)]


def _find_all_instances_reference(res, template_shape, threshold, min_gap):
    """向量化之前的逐像素双层实现，仅作等价性对照与耗时基准，不参与生产调用。"""
    th, tw = template_shape
    loc = []
    h, w = res.shape[:2]
    for y in range(h):
        for x in range(w):
            if res[y, x] >= threshold:
                cx, cy = x + tw // 2, y + th // 2
                too_close = False
                for ex, ey in loc:
                    if abs(cx - ex) < min_gap and abs(cy - ey) < min_gap:
                        too_close = True
                        break
                if not too_close:
                    loc.append((cx, cy))
    loc.sort(key=lambda p: p[1])
    return loc


def test_find_all_instances_matches_reference_implementation(clean_state, monkeypatch):
    """向量化实现必须与旧双层循环逐点等价：含多个峰、阈值边界与近邻抑制。"""
    res = np.zeros((24, 28), np.float32)
    res[0, 0] = 0.5    # 恰等于阈值：保留
    res[0, 1] = 0.9    # 与 (2,2) 相邻（dx=1, dy=0）：被抑制
    res[3, 1] = 0.49   # 低于阈值：丢弃
    res[0, 8] = 0.8    # x 与 (2,2) 相距 8：独立实例
    res[1, 8] = 0.85   # 与 (10,2) 相邻：被抑制
    res[8, 0] = 0.7    # y 与 (2,2) 相距 8：独立实例
    res[8, 8] = 0.6    # 独立实例
    res[8, 9] = 0.55   # 与 (10,10) 相邻：被抑制
    res[0, 14] = 0.9   # 与 (10,2) 的 dx 恰为 min_gap(=6)：`<` 判定不算太近 → 保留
    res[7, 25] = 0.5   # 恰等于阈值：保留
    res[12, 24] = 0.49  # 低于阈值：丢弃
    res[20, 25] = 0.9  # 右下角独立实例
    img = _patch_matcher(monkeypatch, res)

    got = flow_migong.find_all_instances_mg("x", threshold=0.5, min_gap=6, img=img)
    expected = _find_all_instances_reference(res, (5, 5), 0.5, 6)
    assert got == expected


def test_find_all_instances_vectorized_within_budget(clean_state, monkeypatch):
    """锁住「不要退回 O(像素) 的 Python 双层循环」。

    本机实测（20x24 res、5x5 模板、min_gap=6、50 次均值）：旧双层实现
    0.053–0.085 ms，向量化 0.010–0.023 ms。审计预估的「旧实现 1–3 ms」在本
    尺寸不成立，单靠 `< 1 ms` 无法让旧实现失败；因此另加一条对参考实现的
    2 倍加速断言，负验证（换回双层循环）时它才会真正变红。
    """
    res = np.zeros((20, 24), np.float32)
    res[0, 0] = 0.9
    res[1, 1] = 0.9
    res[8, 12] = 0.8
    res[16, 4] = 0.7
    img = _patch_matcher(monkeypatch, res)
    # 模板路径解析与本例无关，桩掉以免把路径开销算进耗时
    monkeypatch.setattr(flow_migong, "tpl", lambda name: name)
    kwargs = {"threshold": 0.5, "min_gap": 6, "img": img}

    flow_migong.find_all_instances_mg("x", **kwargs)  # 预热 argwhere / 桩调用

    def _average(func):
        start = time.perf_counter()
        for _ in range(50):
            func()
        return (time.perf_counter() - start) / 50

    vector_avg = _average(lambda: flow_migong.find_all_instances_mg("x", **kwargs))
    reference_avg = _average(
        lambda: _find_all_instances_reference(res, (5, 5), 0.5, 6)
    )

    assert vector_avg < 0.001, f"向量化平均 {vector_avg * 1000:.4f} ms，超过 1 ms 门槛"
    assert vector_avg * 2 < reference_avg, (
        f"向量化 {vector_avg * 1000:.4f} ms 未显著快于旧实现 "
        f"{reference_avg * 1000:.4f} ms"
    )


# ============================================================
# handle_failure：清理序列 + 长按次数 + 挑战次数透传
# ============================================================
def _stub_failure_seams(monkeypatch, cj_pos, likai_pos):
    """桩掉点击/查找/拖拽/坐标原语，只记录标签与坐标，不碰屏幕与 IPC 文件。"""
    labels = []
    drags = []
    coords = []

    def _fake_click(template_path, label=None, threshold=None, timeout=None):
        labels.append(label)
        return True

    # handle_failure 依次 wait_mg("changanjieshu") 与 wait_mg("likaimigong")
    wait_results = iter([cj_pos, likai_pos])
    monkeypatch.setattr(flow_migong, "click_template", _fake_click)
    monkeypatch.setattr(flow_migong, "wait_mg",
                        lambda name, timeout=None, threshold=None: next(wait_results))
    monkeypatch.setattr(flow_migong, "send_drag",
                        lambda *args, **kwargs: drags.append((args, kwargs)))
    monkeypatch.setattr(flow_migong, "send_coord",
                        lambda x, y: coords.append((x, y)))
    return labels, drags, coords


def test_handle_failure_closes_exits_and_returns_decremented_count(monkeypatch):
    """实测契约：handle_failure 本身不判上限，只做 关弹窗→结束探索→长按→离迷宫
    的清理序列，最后原样返回 challenges_left_func() 的结果交给外层循环判 <=0。"""
    monkeypatch.setattr(flow_migong, "_run_params", {})
    monkeypatch.setattr(flow_migong, "_config", {"drag_repeat": 2})
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    labels, drags, coords = _stub_failure_seams(monkeypatch, cj_pos=(100, 200),
                                                 likai_pos=(300, 400))
    left = {"count": 2}

    def _decrement():
        left["count"] -= 1
        return left["count"]

    assert flow_migong.handle_failure(_decrement) == 1
    assert labels == ["dianjikongbaiguanbi(失败)", "jieshutansuo2"]
    # changanjieshu 长按 drag_repeat(=2) 次，每次 4000ms
    assert len(drags) == 2
    assert all(args == (100, 200, 100, 200) and kwargs["hold_ms"] == 4000
               for args, kwargs in drags)
    assert coords == [(300, 400)]


def test_handle_failure_skips_clicks_when_dialogs_absent(monkeypatch):
    """changanjieshu / likaimigong 都没等到时必须跳过长按与离开点击，不能盲点 None 坐标。"""
    monkeypatch.setattr(flow_migong, "_run_params", {})
    monkeypatch.setattr(flow_migong, "_config", {})
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    labels, drags, coords = _stub_failure_seams(monkeypatch, cj_pos=None,
                                                likai_pos=None)

    assert flow_migong.handle_failure(lambda: 0) == 0
    assert labels == ["dianjikongbaiguanbi(失败)", "jieshutansuo2"]
    assert drags == []
    assert coords == []


# ============================================================
# flow_migong 外层循环：失败后次数上限
# ============================================================
def _stub_flow_entry(monkeypatch):
    """桩掉一次性进入与单场挑战，只保留外层次数判定；返回 (root_clicks, mg_clicks)。"""
    root_clicks = []
    mg_clicks = []

    def _fake_wait_click(template_path, name, *args, **kwargs):
        root_clicks.append(name)
        return True

    def _fake_click(template_path, label=None, threshold=None, timeout=None):
        mg_clicks.append(label)
        return True

    monkeypatch.setattr(flow_migong, "load_config", lambda: None)
    monkeypatch.setattr(flow_migong, "click_and_wait", lambda *args, **kwargs: True)
    # click_root 直接走模块级 wait_and_click
    monkeypatch.setattr(flow_migong, "wait_and_click", _fake_wait_click)
    monkeypatch.setattr(flow_migong, "click_template", _fake_click)
    # _find_root 恒命中：fanfanle2 检测循环首轮即 break，不空转 1.5s
    monkeypatch.setattr(flow_migong, "_find_root",
                        lambda name, threshold=None: (0, 0))
    # 失败清理整段是屏幕交互，已在上面单独测过；这里只保留次数递减语义
    monkeypatch.setattr(flow_migong, "handle_failure", lambda func: func())
    return root_clicks, mg_clicks


def test_flow_stops_challenging_when_count_exhausted(clean_state, monkeypatch):
    """剩 1 次且失败：handle_failure 返回 0 → break，不得再点 jinru 续挑战。"""
    root_clicks, mg_clicks = _stub_flow_entry(monkeypatch)
    challenge_calls = []

    def _always_fail():
        challenge_calls.append(1)
        return "fail"

    monkeypatch.setattr(flow_migong, "run_one_challenge", _always_fail)
    flow_migong.flow_migong(challenges=1)

    assert len(challenge_calls) == 1
    assert "jinru(失败后)" not in mg_clicks
    # 次数耗尽后直接走四步退出
    assert root_clicks == ["renwu", "exit", "exitck", "exitck2", "exit3"]


def test_flow_continues_when_challenges_remain(clean_state, monkeypatch):
    """剩 2 次且首轮失败：应点 jinru(失败后) 续挑战，第二轮成功后正常退出。"""
    root_clicks, mg_clicks = _stub_flow_entry(monkeypatch)
    results = iter(["fail", "done"])
    monkeypatch.setattr(flow_migong, "run_one_challenge", lambda: next(results))

    flow_migong.flow_migong(challenges=2)

    assert mg_clicks == ["qianwang", "jinru(失败后)"]
    assert root_clicks == ["renwu", "exit", "exitck", "exitck2", "exit3"]
