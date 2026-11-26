"""2026-11-25 实机三处修复的回归用例。

1. 截图失败重试：08:42 解锁瞬间 Pillow 抛 `screen grab failed`，幻灵推图整项报废，
   异常恢复路径再截一次又失败，把整个运行线程也带走了。
2. 巅峰竞技场观战上限：08:13:55 点「战斗」，300 秒判超时，而失败现场（26 秒后）
   已经是主界面——这一场打了 5 分钟以上，300 秒只差一点点。
3. 爬塔进塔确认：自然之塔第一次点击其实已进塔（补点找不到卡片），但塔内「爬塔挑战」
   没按 0.9 认出来，整座塔被跳过；塔卡片全消失时应交给 flow_tower 处理。
"""
import os
import sys
import types

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common
import dianfengjingjichang
import pata

# ===== 1. 截图失败重试 =====

def _fake_frame():
    return np.zeros((40, 60, 3), dtype=np.uint8)


def _stub_capture(monkeypatch, failures):
    """后台截图恒不可用，普通截图先失败 failures 次再成功。"""
    monkeypatch.setattr(common, "_background_screenshot", lambda: None)
    monkeypatch.setattr(common, "ensure_game_clickable", lambda: None)
    monkeypatch.setattr(common, "_stop_background_capture", lambda: None)
    monkeypatch.setattr(common, "_sleep_interruptible", lambda _seconds: None)
    common.invalidate_screenshot_cache()
    logs = []
    monkeypatch.setattr(common, "log", logs.append)
    calls = {"grab": 0}

    def fake_grab():
        calls["grab"] += 1
        if calls["grab"] <= failures:
            raise OSError("screen grab failed")
        return _fake_frame()

    monkeypatch.setattr(common.pyautogui, "screenshot", fake_grab)
    return calls, logs


def test_screenshot_retries_through_transient_grab_failure(monkeypatch):
    """短暂失败（锁屏/解锁、切分辨率）应被重试跨过，而不是让任务失败。"""
    calls, logs = _stub_capture(monkeypatch, failures=2)

    img = common.screenshot_bgr()

    assert img.shape == (40, 60, 3)
    assert calls["grab"] == 3
    assert any("截图失败" in message for message in logs)


def test_screenshot_gives_up_after_retry_budget(monkeypatch):
    """持续不可用时按预算放弃，异常仍向上抛，交给任务层记失败。"""
    calls, _logs = _stub_capture(monkeypatch, failures=99)

    try:
        common.screenshot_bgr()
    except OSError as exc:
        assert "screen grab failed" in str(exc)
    else:
        raise AssertionError("重试用尽后应抛出 OSError")
    assert calls["grab"] == common.SCREENSHOT_RETRY_ATTEMPTS


# ===== 2. 巅峰竞技场观战上限 =====

def test_battle_wait_covers_five_minute_fights():
    """2026-11-25：这场打了 5 分钟以上，300 秒上限在结束前一秒超时。"""
    assert dianfengjingjichang.MAX_BATTLE_TIME >= 600
    assert dianfengjingjichang.BATTLE_STALL_LIMIT == int(
        dianfengjingjichang.MAX_BATTLE_TIME / dianfengjingjichang.OUTCOME_POLL
    )


# ===== 3. 爬塔进塔确认 =====

def _stub_pata(monkeypatch, tower_card_persists):
    """跑一条只有自然之塔的爬塔流程；记录 flow_tower 是否被调用。"""
    called = {"flow_tower": 0}
    fake_flow = types.ModuleType("flow_tower")
    fake_flow.flow_tower = lambda: called.__setitem__("flow_tower", called["flow_tower"] + 1)
    fake_jiance = types.ModuleType("jiance")
    fake_jiance.check_and_handle_libao = lambda **kwargs: None
    monkeypatch.setitem(sys.modules, "flow_tower", fake_flow)
    monkeypatch.setitem(sys.modules, "jiance", fake_jiance)

    monkeypatch.setattr(pata, "recover_to_main_interface", lambda: True)
    monkeypatch.setattr(pata, "open_wanfamulu", lambda **kwargs: True)
    monkeypatch.setattr(pata, "random_sleep", lambda: None)
    monkeypatch.setattr(pata, "scroll_in_client_region", lambda *a, **k: None)
    monkeypatch.setattr(pata, "is_loading_screen", lambda: False)
    monkeypatch.setattr(pata, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(pata, "log", lambda message: None)
    # 「卡片消失但认不出挑战按钮」现在会顺手存一张现场图，测试里不能去截真实屏幕
    dumps = []
    monkeypatch.setattr(pata, "capture_failure_context",
                        lambda *args, **kwargs: dumps.append(args))
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    # 「天穹试炼」入口点击成功，进塔点击一律失败（模拟今天认不出「爬塔挑战」）
    monkeypatch.setattr(
        pata, "click_and_confirm",
        lambda path, name, *a, **k: "爬塔入口" in name,
    )

    card_hits = {"count": 0}

    def fake_find(template_path, threshold=0.8, *args, **kwargs):
        if template_path == pata.tpl_pata:
            return (700, 400)
        if template_path == pata.tpl_ziranzhita:
            card_hits["count"] += 1
            # 第一次是「检测塔卡片」，之后是「确认是否还在选择页」
            if card_hits["count"] == 1 or tower_card_persists:
                return (640, 300)
            return None
        return None

    monkeypatch.setattr(pata, "find_center_silent", fake_find)
    return called, dumps


def test_pata_enters_tower_when_confirm_failed_but_cards_gone(monkeypatch):
    """塔卡片已消失=已离开选择页：不能因为没认出「爬塔挑战」就丢掉这座塔。"""
    called, dumps = _stub_pata(monkeypatch, tower_card_persists=False)

    assert pata.flow_pata() is True
    assert called["flow_tower"] == 1
    # 连续三天都卡在这一步，进塔后必须留一张现场图供第二天定位
    assert len(dumps) == 1


def test_pata_skips_tower_when_still_on_select_page(monkeypatch):
    """仍停在选择页（点击真被吞掉）时保持原行为：跳过该塔，不误调 flow_tower。"""
    called, dumps = _stub_pata(monkeypatch, tower_card_persists=True)

    assert pata.flow_pata() is True
    assert called["flow_tower"] == 0
    assert dumps == []
