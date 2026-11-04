"""warehouse 纯逻辑单元测试：多尺度步长生成、退化输入降级、仓库文本跨模块契约。

只测决策与计算逻辑（不依赖游戏窗口/真实模板）；像素阈值本身只能实跑验证，
但 has_fancy_border / _top_band_edge_count 只吃传入的 ROI 数组，可用合成图测边界分支。
"""
import numpy as np
import pytest

import flow_tower
import warehouse

# === _iter_scales：步长生成器的三条契约 ===

def test_iter_scales_yields_nothing_when_step_not_positive():
    """step <= 0 必须产出空——这是防死循环的保护（s 永远不前进），重构最容易被删。

    用 next() 而非 list() 断言：判据被改成 step < 0 时生成器会无限产出，
    list() 会挂死测试进程，next() 则立即失败。
    """
    for step in (0.0, -0.05):
        scales = warehouse._iter_scales(0.9, 1.1, step)
        with pytest.raises(StopIteration):
            next(scales)


def test_iter_scales_includes_upper_bound_despite_float_drift():
    """0.0 起步、步长 0.1 走到 0.3 时浮点累加值为 0.30000000000000004，
    靠 +1e-9 容差才能包含上界；去掉容差会少扫一个尺度（_best_multiscale 的循环次数由它决定）。
    """
    assert list(warehouse._iter_scales(0.0, 0.3, 0.1)) == [0.0, 0.1, 0.2, 0.3]


def test_iter_scales_rounds_values_to_four_decimals():
    """产出必须经 round(s, 4)：0.9+0.05 的浮点结果是 0.9500000000000001，不修就会随步数漂移。

    0.90–1.10/步长 0.05 即仓库扫描默认尺度（HERO_TEMPLATE_SCALE_*），共 5 档。
    """
    assert list(warehouse._iter_scales(0.90, 1.10, 0.05)) == [0.9, 0.95, 1.0, 1.05, 1.1]


# === _best_multiscale_match_score：退化输入必须安静返回 -1.0 而不是崩在 cv2 ===

def test_multiscale_returns_minus_one_on_none_input():
    """任一侧为 None 时 early return；去掉判据会 AttributeError 崩在 .shape[:2]，
    模板缺失时仓库扫描应降级而不是整个中断。
    """
    search = np.zeros((50, 50, 3), dtype=np.uint8)
    tpl = np.zeros((10, 10, 3), dtype=np.uint8)
    assert warehouse._best_multiscale_match_score(None, tpl) == -1.0
    assert warehouse._best_multiscale_match_score(search, None) == -1.0


def test_multiscale_returns_minus_one_on_undersized_image():
    """任意一边高或宽 < 2 时返回 -1.0。

    用 1 行高模板 × 4 倍尺度：若去掉 <2 的 early return，模板会被合法放大到 4×40
    并进入 matchTemplate——实测纯色图返回 1.0（零方差图 TM_CCOEFF_NORMED 归一化为 1），
    于是「识别不到的坏输入」被误报成满分匹配，比崩溃更隐蔽。
    """
    search = np.zeros((50, 50, 3), dtype=np.uint8)
    assert warehouse._best_multiscale_match_score(
        search, np.zeros((1, 10, 3), dtype=np.uint8), 4.0, 4.0, 1.0) == -1.0
    assert warehouse._best_multiscale_match_score(
        np.zeros((50, 1, 3), dtype=np.uint8), search, 1.0, 1.0, 1.0) == -1.0


def test_multiscale_skips_scale_larger_than_search():
    """所有尺度下模板都大于搜索图时走 continue 分支，最终仍返回 -1.0 而不是抛错。"""
    search = np.zeros((10, 10, 3), dtype=np.uint8)
    tpl = np.zeros((100, 100, 3), dtype=np.uint8)
    assert warehouse._best_multiscale_match_score(search, tpl, 1.0, 1.0, 1.0) == -1.0


# === warehouse._save_heroes_to_txt 与 flow_tower._load_warehouse_levels 的文本契约 ===

def test_warehouse_txt_roundtrip_between_modules(tmp_path, monkeypatch):
    """warehouse 写「名字,档位」、flow_tower 按逗号解析，两边无共享代码，格式一变就是静默数据损坏。

    覆盖 docstring 里的映射：有花边→高、平框→低、ALL_HERO_NAMES 里未识别的→未拥有；
    hero_dict 里不在 ALL_HERO_NAMES 的键不写盘（识别只产基础名，属正常路径）。
    """
    txt_path = str(tmp_path / "warehouse_heroes.txt")
    # 必须猴补丁到临时目录：WAREHOUSE_TXT_PATH 默认指向仓库里版本控制的真实数据文件
    monkeypatch.setattr(warehouse, "WAREHOUSE_TXT_PATH", txt_path)
    monkeypatch.setattr(warehouse, "ALL_HERO_NAMES", ["nvyao", "wuyue"])
    monkeypatch.setattr(flow_tower, "WAREHOUSE_TXT_PATH", txt_path)

    warehouse._save_heroes_to_txt({"nvyao": "有花边", "不在清单": "平框"})

    levels = flow_tower._load_warehouse_levels()
    assert levels == {"nvyao": "高", "wuyue": "未拥有"}


# === 边框判定：只吃传入 ROI，可用合成图测 ===

def test_uniform_roi_not_fancy_border_but_framed_roi_is():
    """has_fancy_border 只依赖传入的 card_roi 与显式阈值参数，无模块级状态。

    纯黑 ROI 上边框区 Canny 边缘数为 0：empty_thresh=10 时应判空槽 None，
    empty_thresh=0 时应判平框 False；外圈 3 像素画白框的 ROI 边缘约 81 个，应判有花边 True。
    """
    uniform = np.zeros((100, 75, 3), dtype=np.uint8)
    assert warehouse.has_fancy_border(uniform, border_thickness=3,
                                      empty_thresh=0, fancy_thresh=50) is False
    assert warehouse.has_fancy_border(uniform, border_thickness=3,
                                      empty_thresh=10, fancy_thresh=50) is None

    framed = np.zeros((100, 75, 3), dtype=np.uint8)
    framed[0:3, :] = 255
    framed[:, 0:3] = 255
    framed[:, -3:] = 255
    assert warehouse.has_fancy_border(framed, border_thickness=3,
                                      empty_thresh=10, fancy_thresh=50) is True


def test_top_band_edge_count_uniform_none_and_framed():
    """_top_band_edge_count 契约：None 或纯色 ROI 计 0（降级安全），带亮边框的 ROI 明显大于 0。"""
    assert warehouse._top_band_edge_count(None) == 0
    assert warehouse._top_band_edge_count(np.zeros((100, 75, 3), dtype=np.uint8)) == 0

    framed = np.zeros((100, 75, 3), dtype=np.uint8)
    framed[0:3, :] = 255
    assert warehouse._top_band_edge_count(framed) > warehouse.BORDER_EDGE_THRESHOLD
