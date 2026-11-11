"""2026-11-11 实机回归：点击全不准的物理根因 + 塔/悬赏两处误判。

负验证留痕（把对应修复改回去，下列用例必须失败）：
- `common.ensure_game_clickable` 改回「激活后 sleep(0.25) 就返回」→
  `test_ensure_clickable_reports_foreground_lock` 必须失败；
- `send_coord` 去掉「前台锁时点标题栏补激活」→
  `test_send_coord_clicks_title_bar_when_lock_blocks` 与
  `test_send_coord_skips_title_bar_when_already_front` 必须失败；
- `pata` 进入塔的确认判据改回 `_left_catalog_page`（只判「玩法目录」标题消失）→
  `test_pata_confirm_uses_tower_page_marker` 必须失败；
- `lieshouxunshang._panel_still_here` 改回「只认面板标题」→
  `test_hunt_panel_ok_when_settlement_popup_covers_title` 必须失败；
- `flow_tower` 主循环去掉「关掉结算弹窗后重试挑战按钮」→
  `test_flow_tower_retries_after_settlement_popup` 必须失败。
"""
import os
from pathlib import Path

import common
import lieshouxunshang
import pata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_source(relative_path):
    return (Path(ROOT) / relative_path).read_text(encoding="utf-8")


# ---------- 前台锁：激活必须被确认 ----------

def test_ensure_clickable_reports_foreground_lock(monkeypatch):
    """SetForegroundWindow 被前台锁挡下时，必须返回 False 而不是「当成功」。"""
    class _User32:
        def IsIconic(self, _hwnd):
            return 0

        def GetForegroundWindow(self):
            return 999   # 始终不是游戏窗口：模拟前台锁

        def ShowWindow(self, *_a):
            return 1

    monkeypatch.setattr(common, "find_game_window", lambda: 123)
    monkeypatch.setattr(common, "_activate_game_window", lambda _h: None)
    monkeypatch.setitem(common._auto_activate, "enabled", True)
    monkeypatch.setattr(common.ctypes, "windll", type("W", (), {"user32": _User32()}))
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)

    assert common.ensure_game_clickable() is False


def test_ensure_clickable_true_when_already_front(monkeypatch):
    class _User32:
        def IsIconic(self, _hwnd):
            return 0

        def GetForegroundWindow(self):
            return 123

    monkeypatch.setattr(common, "find_game_window", lambda: 123)
    monkeypatch.setitem(common._auto_activate, "enabled", True)
    monkeypatch.setattr(common.ctypes, "windll", type("W", (), {"user32": _User32()}))

    assert common.ensure_game_clickable() is True


# ---------- send_coord：前台锁时先点标题栏 ----------

def test_send_coord_clicks_title_bar_when_lock_blocks(monkeypatch):
    """前台锁未解开时，必须先用「点标题栏」补激活，再点目标。"""
    calls = []
    monkeypatch.setitem(common._auto_activate, "enabled", True)
    monkeypatch.setattr(common, "ensure_game_clickable", lambda: False)
    monkeypatch.setattr(common, "_click_title_bar", lambda: calls.append("title") or True)
    monkeypatch.setattr(common, "_restore_cursor", {"enabled": False})
    monkeypatch.setattr(common, "point_owned_by_game", lambda _x, _y: True)
    monkeypatch.setattr(common, "_write_coord_raw", lambda x, y, **_k: calls.append((x, y)) or True)
    monkeypatch.setattr(common, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)

    common.send_coord(111, 222)
    assert calls[0] == "title", "前台锁下必须先点标题栏激活，否则第一次点击会被吞"
    assert calls[-1] == (111, 222)


def test_send_coord_skips_title_bar_when_already_front(monkeypatch):
    calls = []
    monkeypatch.setitem(common._auto_activate, "enabled", True)
    monkeypatch.setattr(common, "ensure_game_clickable", lambda: True)
    monkeypatch.setattr(common, "_click_title_bar", lambda: calls.append("title") or True)
    monkeypatch.setattr(common, "_restore_cursor", {"enabled": False})
    monkeypatch.setattr(common, "point_owned_by_game", lambda _x, _y: True)
    monkeypatch.setattr(common, "_write_coord_raw", lambda x, y, **_k: calls.append((x, y)) or True)
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)

    common.send_coord(333, 444)
    assert "title" not in calls
    assert calls == [(333, 444)]


def test_title_bar_click_uses_area_above_client(monkeypatch):
    """标题栏点击必须落在客户区之外，否则会误触游戏内按钮。"""
    written = {}
    monkeypatch.setattr(common, "find_game_window", lambda: 7)
    monkeypatch.setattr(common, "_client_rect_of", lambda _h: (2212, 76, 1600, 900))

    class _U:
        def GetWindowRect(self, _h, ref):
            ref._obj.left, ref._obj.top = 2204, 45
            ref._obj.right, ref._obj.bottom = 3820, 984
            return 1

    monkeypatch.setattr(common.ctypes, "windll", type("W", (), {"user32": _U()}))
    monkeypatch.setattr(common, "_write_coord_raw",
                        lambda x, y, **_k: written.update(x=x, y=y) or True)
    monkeypatch.setattr(common.time, "sleep", lambda _s: None)

    assert common._click_title_bar() is True
    assert written["y"] < 76, "标题栏点击点必须高于客户区上边界"


# ---------- 爬塔：进入塔的确认判据 ----------

def test_pata_confirm_uses_tower_page_marker():
    """进入塔必须用塔内独有的「挑战」按钮确认，不能用「玩法目录标题消失」。"""
    text = _read_source("pata.py")
    call = text[text.index('f"{tower_name}(进入塔)"'):]
    assert "_in_tower_page" in call[:200]
    assert "_left_catalog_page" not in call[:200], (
        "塔选择页同样没有「玩法目录」标题，用它确认会把「没进去」判成「进去了」"
    )


def test_in_tower_page_requires_challenge_button(monkeypatch):
    monkeypatch.setattr(pata, "is_loading_screen", lambda: False)
    monkeypatch.setattr(pata, "find_center_silent", lambda *_a, **_k: None)
    assert pata._in_tower_page() is False

    monkeypatch.setattr(pata, "find_center_silent", lambda *_a, **_k: (3110, 669))
    assert pata._in_tower_page() is True

    monkeypatch.setattr(pata, "is_loading_screen", lambda: True)
    assert pata._in_tower_page() is False, "加载中不能当成已进入塔"


# ---------- 狩猎悬赏：结算弹窗不等于点击被吞 ----------

def test_hunt_panel_ok_when_settlement_popup_covers_title(monkeypatch):
    monkeypatch.setitem(lieshouxunshang._incomplete, "active", True)
    tpl_title = lieshouxunshang.tpl_title
    hint = common.get_template_path("dianjikongbaichuguanbi.png")

    def fake_find(tpl, *_a, **_k):
        return None if tpl == tpl_title else (100, 100)   # 标题压暗，但结算弹窗在

    monkeypatch.setattr(lieshouxunshang, "_find", fake_find)
    assert lieshouxunshang._panel_still_here() is True
    assert hint  # 模板路径存在（判据确实用到它）


def test_hunt_panel_gone_when_nothing_visible(monkeypatch):
    monkeypatch.setitem(lieshouxunshang._incomplete, "active", True)
    monkeypatch.setattr(lieshouxunshang, "_find", lambda *_a, **_k: None)
    assert lieshouxunshang._panel_still_here() is False


# ---------- 爬塔：打完一层后被结算弹窗挡住要重试 ----------

def test_flow_tower_retries_after_settlement_popup():
    text = _read_source("flow_tower.py")
    body = text[text.index("clicked = wait_and_click(tpl_patatiaozhan"):]
    assert "tpl_dianjikongbaichuguanbi" in body[:600], (
        "找不到挑战按钮时必须先关掉结算弹窗再重试，否则会误判「已经推完」"
    )
    assert "patatiaozhan(关弹窗后)" in body[:900]


# ---------- 推图：首通奖励必须在进入备战界面之前领 ----------

def test_push_claims_first_clear_before_entering_mode():
    """首通奖励入口（右上角奖杯）只在推图主界面存在；进了备战页就点不到。"""
    text = _read_source("push.py")
    enter = text.index('if not wait_and_click(tpl_advance, "advance(a)", 0.8):')
    claim = text.index("claim_first_clear_reward()", enter)
    enter_mode = text.index("self._enter_mode_and_confirm()", enter)
    assert claim < enter_mode, (
        "必须先领首通奖励再进模式：进入备战页后奖杯入口消失，"
        "领奖跳转还会把界面退回主界面、打乱状态判据"
    )


# ---------- 翻翻乐：一次点不动不等于钥匙用完 ----------

def test_fanfanle_retries_before_declaring_exhausted(monkeypatch):
    """钥匙还剩 376 把时曾报「已完成 1 轮、钥匙用完」：点不动必须重试，不能一次定论。"""
    import fanfanle

    monkeypatch.setattr(fanfanle, "check_stop", lambda: None)
    monkeypatch.setattr(fanfanle.time, "sleep", lambda _s: None)
    monkeypatch.setattr(fanfanle, "invalidate_screenshot_cache", lambda: None)
    monkeypatch.setattr(fanfanle, "_keys_region_crop", lambda: b"k")
    monkeypatch.setattr(fanfanle, "_region_crop", lambda _r: b"p")

    clicks = []

    def fake_click(*_a, **_k):
        clicks.append(1)
        return True

    # 按钮一直在（钥匙耗尽前它都在），但点了始终没变化 → 必须重试到 CLICK_RETRIES 次
    monkeypatch.setattr(fanfanle, "find_center_silent", lambda *_a, **_k: (100, 200))
    monkeypatch.setattr(fanfanle, "click_position", fake_click)
    monkeypatch.setattr(fanfanle, "_wait_keys_change", lambda *_a, **_k: False)

    assert fanfanle.burn_keys(max_rounds=5) == 0
    assert len(clicks) == fanfanle.CLICK_RETRIES, "没变化必须重试到 CLICK_RETRIES 次才下结论"


def test_fanfanle_counts_round_when_change_detected(monkeypatch):
    import fanfanle

    monkeypatch.setattr(fanfanle, "check_stop", lambda: None)
    monkeypatch.setattr(fanfanle.time, "sleep", lambda _s: None)
    monkeypatch.setattr(fanfanle, "invalidate_screenshot_cache", lambda: None)
    monkeypatch.setattr(fanfanle, "_keys_region_crop", lambda: b"k")
    monkeypatch.setattr(fanfanle, "_region_crop", lambda _r: b"p")
    monkeypatch.setattr(fanfanle, "find_center_silent", lambda *_a, **_k: (100, 200))
    monkeypatch.setattr(fanfanle, "click_position", lambda *_a, **_k: True)

    hits = {"n": 0}

    def changed_once(*_a, **_k):
        hits["n"] += 1
        return hits["n"] <= 2      # 只有前两轮推进得动

    monkeypatch.setattr(fanfanle, "_wait_keys_change", changed_once)
    assert fanfanle.burn_keys(max_rounds=2) == 2
