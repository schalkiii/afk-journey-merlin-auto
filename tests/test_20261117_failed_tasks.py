"""2026-11-17 定时运行两个失败项的修复测试：女神塔重进确认、愿望单家园入口重试。

负验证留痕：
- `_tower_page_open_stable` 去掉第二次确认 → `test_tower_stable_confirm_rejects_flash` 失败；
- `_ensure_panel` 的循环重试家园入口删掉 → `test_wishlist_retries_homestead_in_loop` 失败；
- `_enter_homestead` 的 find_timeout 改回 2.0 → `test_wishlist_homestead_timeout_extended` 失败。
"""
import inspect

import nvshenta
import yuanwangdan


def test_tower_stable_confirm_rejects_flash(monkeypatch):
    """切换瞬间单帧可见不算打开；间隔 settle 后仍可见才算。"""
    results = [True, False]  # 第一次可见，第二次已切走
    monkeypatch.setattr(nvshenta, "_tower_page_open", lambda: results.pop(0))
    monkeypatch.setattr(nvshenta.time, "sleep", lambda _s: None)
    assert nvshenta._tower_page_open_stable(settle=0.1) is False


def test_tower_stable_confirm_accepts_persistent(monkeypatch):
    monkeypatch.setattr(nvshenta, "_tower_page_open", lambda: True)
    monkeypatch.setattr(nvshenta.time, "sleep", lambda _s: None)
    assert nvshenta._tower_page_open_stable(settle=0.1) is True


def test_reentry_uses_stable_confirm():
    """重进女神塔的 click_and_confirm 必须用稳定判据，不能用单帧判据。

    2026-11-24 起重进动作抽到 `_reenter_tower()`（回退与重进共用），
    断言改查这个函数的源码；契约本身不变：必须用 `_tower_page_open_stable`。
    """
    source = inspect.getsource(nvshenta._reenter_tower)
    assert "click_and_confirm(tpl_nvshenta" in source
    assert "_tower_page_open_stable" in source, "单帧判据会把玩法目录误认成塔页面"


def test_wishlist_retries_homestead_in_loop():
    """找不到立牌且在主界面时，每轮都要重试点家园入口（原来只在开头点一次）。"""
    source = inspect.getsource(yuanwangdan._ensure_panel)
    assert "at_main_interface() and _enter_homestead()" in source


def test_wishlist_homestead_timeout_extended():
    """家园入口 find_timeout 必须 >2 秒，覆盖切回主界面后的渲染延迟。"""
    code_lines = [line for line in inspect.getsource(yuanwangdan._enter_homestead).splitlines()
                  if not line.strip().startswith("#")]
    code = "\n".join(code_lines)
    assert "find_timeout=6.0" in code
    assert "find_timeout=2.0" not in code
