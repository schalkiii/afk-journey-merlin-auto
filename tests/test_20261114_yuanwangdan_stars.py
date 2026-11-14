"""家园愿望单「今日星星已满即完成」的回归测试。

背景（2026-11-14 实跑）：交付到 20 单（`MAX_ORDERS`）就停，面板里还留着订单，看起来没做完；
而面板左上角星级进度其实已经是 **70/70 且带完成徽章**——每日阶梯 5 / 20 / 40 / 70 颗星
已全部领完，再交付只烧材料、不涨任何每日进度。故把「星级已满」取为真·完成线，
并且这种情形必须记成功（不是失败），否则每天都在报假故障。

负验证留痕（改坏实现，用例必须变红）：
1. `_daily_stars_done` 改成恒 `return False` →
   `test_main_marks_success_when_stars_already_full` 变红（空跑到底还判失败）；
2. `main()` 结尾的 `return delivered > 0 or stars_full` 去掉 `or stars_full` → 同上变红；
3. `_daily_stars_done` 去掉 `client_region` 限定（全屏搜索）→
   `test_daily_stars_done_limits_search_region` 变红。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yuanwangdan


def test_daily_stars_done_true_when_badge_visible(monkeypatch):
    monkeypatch.setattr(yuanwangdan, "find_center_silent", lambda *a, **k: (474, 60))
    assert yuanwangdan._daily_stars_done() is True


def test_daily_stars_done_false_when_badge_absent(monkeypatch):
    monkeypatch.setattr(yuanwangdan, "find_center_silent", lambda *a, **k: None)
    assert yuanwangdan._daily_stars_done() is False


def test_daily_stars_done_limits_search_region(monkeypatch):
    """判据必须限定在星级进度条那一小块，否则别的面板上的绿色勾会被误当成「已满」。"""
    seen = {}

    def fake_find(template_path, threshold=0.8, **kwargs):
        seen["path"] = template_path
        seen["threshold"] = threshold
        seen["client_region"] = kwargs.get("client_region")

    monkeypatch.setattr(yuanwangdan, "find_center_silent", fake_find)
    yuanwangdan._daily_stars_done()

    assert seen["path"] == yuanwangdan.tpl_stars_full
    assert seen["client_region"] == yuanwangdan.STARS_CLIENT_REGION
    assert seen["threshold"] >= 0.85


def test_main_marks_success_when_stars_already_full(monkeypatch):
    """开局就满星：一单不交也要记成功，并在日志里说清原因。

    直接对 `log` 打桩而不是抓 stdout——整套用例一起跑时，别的用例会把日志出口
    （`log_format` 的 sink）切走，`capsys` 抓不到，单独跑却正常（2026-11-14 门禁踩过）。
    """
    messages = []

    monkeypatch.setattr(yuanwangdan, "_ensure_panel", lambda: True)
    monkeypatch.setattr(yuanwangdan, "_daily_stars_done", lambda: True)
    monkeypatch.setattr(yuanwangdan, "check_stop", lambda: None)
    monkeypatch.setattr(yuanwangdan, "_find", lambda *a, **k: None)
    monkeypatch.setattr(yuanwangdan, "flow_return_main", lambda: None)
    monkeypatch.setattr(yuanwangdan, "log", messages.append)
    monkeypatch.setattr(yuanwangdan.time, "sleep", lambda *a, **k: None)

    assert yuanwangdan.main() is True
    assert any("70/70" in msg and "已满" in msg for msg in messages), messages
