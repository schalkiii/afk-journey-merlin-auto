"""2026-11-10 实机失败修复回归：点击稳定性 + 「误报成功」治理。

负验证留痕：
- 把 AHK 注入器脚本改回「读走坐标即删文件 + Click 瞬时 down/up + 慢速 MouseMove」，
  `test_ahk_script_has_steady_click` 必须失败；
- 把狩猎悬赏 `main()` 改回无条件 `return True`，`test_hunt_reports_false_when_blocked` 必须失败；
- 把好友奖励 `main()` 改回无条件 `return True`，`test_friend_reports_false_when_gift_unfinished` 必须失败；
- 删掉翻翻乐的「点任务后确认面板打开」，`test_fanfanle_retries_task_entry` 必须失败；
- 把爬塔改回一次滚两下，`test_pata_scrolls_one_step_at_a_time` 必须失败；
- 把 `common.click_and_confirm` 改回「点一次就返回 True」，
  `test_click_and_confirm_reclicks_until_confirmed` 必须失败；
- 把好友奖励改回「点社交后 sleep 2 秒查一次就终止」，
  `test_friend_reclicks_social_when_panel_missing` 与
  `test_friend_falls_back_to_hud_when_social_never_opens` 必须失败；
- 去掉推图 `_clear_occluder` 的 autocha/guajijixian 误点保护，
  `test_push_clears_popup_without_close_hint` 必须失败。
"""
import os
import time
from pathlib import Path

import pytest

import haoyoujiangli
import lieshouxunshang

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_source(relative_path):
    """读源码文本（用作源码级断言，避免 import GUI 依赖）。"""
    return (Path(ROOT) / relative_path).read_text(encoding="utf-8")


# ---------- 点击注入器 ----------

def test_ahk_script_has_steady_click():
    """新 AHK 脚本必须：瞬移、按下保持、动作完成后才删 IPC 文件。"""
    path = os.path.join(ROOT, "click_from_file.ahk")
    assert os.path.exists(path), "缺少明文 AHK 注入器脚本"
    text = _read_source("click_from_file.ahk")
    # AHK v2 合法写法：Click "Down"/"Up" 作用于当前光标位置，先 MouseMove 到目标点
    assert 'Click "Down"' in text
    assert "Sleep clickHoldDelay" in text
    assert 'Click "Up"' in text
    # FileDelete 必须在 Up 之后（文件消失 == 点击完成），不能像旧 exe 那样读走就删
    assert text.index("FileDelete coordPath") > text.index('Click "Up"')
    assert "MouseMove x, y, 0" in text, "慢速滑动会让光标漂，必须瞬移"
    assert "OnExit ReleaseLeft" in text, "退出时必须释放可能按下的左键"


def test_spec_bundles_ahk_script():
    spec = _read_source("goldenhandmaidens.spec")
    assert "('click_from_file.ahk', '.')" in spec


# ---------- 误报成功治理 ----------

def test_hunt_reports_false_when_blocked(monkeypatch):
    """动作被弹框遮挡且未恢复时，狩猎悬赏不能再报成功。"""
    monkeypatch.setattr(lieshouxunshang, "_enter_panel", lambda: True)
    monkeypatch.setattr(lieshouxunshang, "_use_own_searches", lambda: 3)
    monkeypatch.setattr(lieshouxunshang, "_join_others", lambda: 1)
    monkeypatch.setattr(lieshouxunshang, "_find", lambda *a, **k: None)
    monkeypatch.setattr(lieshouxunshang, "click_position", lambda *a, **k: True)
    monkeypatch.setattr(lieshouxunshang, "check_and_handle_libao", lambda *a, **k: None)
    monkeypatch.setattr(lieshouxunshang, "flow_return_main", lambda *a, **k: True)
    monkeypatch.setattr(lieshouxunshang, "log", lambda *a, **k: None)

    def blocked():
        lieshouxunshang._incomplete["flag"] = True

    monkeypatch.setattr(lieshouxunshang, "_join_others", blocked)
    assert lieshouxunshang.main() is False
    assert lieshouxunshang._incomplete["active"] is False, "任务结束必须复位任务级 guard"


def test_hunt_guard_inactive_outside_main(monkeypatch):
    """直接调子流程时不启用遮挡 guard（避免依赖截图/点击）。"""
    assert lieshouxunshang._incomplete["active"] is False
    monkeypatch.setattr(lieshouxunshang, "_find", lambda *a, **k: None)
    assert lieshouxunshang._dismiss_blocking_popup() is None
    assert lieshouxunshang._panel_still_here() is True


def test_friend_reports_false_when_gift_unfinished(monkeypatch):
    """一键赠礼按钮仍在却点不掉时，好友奖励不能报成功。"""
    monkeypatch.setattr(haoyoujiangli, "find_center", lambda *a, **k: (1, 1))
    monkeypatch.setattr(haoyoujiangli, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(haoyoujiangli, "send_coord", lambda *a, **k: None)
    monkeypatch.setattr(haoyoujiangli, "_collect_gifts", lambda: 0)
    monkeypatch.setattr(haoyoujiangli, "_close_popups", lambda: None)
    monkeypatch.setattr(haoyoujiangli, "_claim_friend_rewards", lambda: 0)
    monkeypatch.setattr(haoyoujiangli, "flow_return_main", lambda: True)
    monkeypatch.setattr(haoyoujiangli.time, "sleep", lambda _s: None)
    assert haoyoujiangli.main() is False


# ---------- 面板进入确认 / 滚动不过头 ----------

def test_fanfanle_retries_task_entry():
    """翻翻乐进面板前必须确认任务面板打开（源码级，避免每次 import GUI 依赖）。"""
    text = _read_source("fanfanle.py")
    assert "from hongbaolingqu import _panel_open" in text
    assert 'wait_and_click(tpl_task_tab, "任务(补点)"' in text


def test_pata_scrolls_one_step_at_a_time():
    """爬塔/公会玩法改回「一次滚两下」会滚过头，本用例钉住逐次下滑。"""
    text = _read_source("pata.py")
    assert 'scroll_in_client_region("down", times=1)' in text
    assert 'scroll_in_client_region("down", times=2)' not in text


def test_ahk_launcher_priority_configured():
    """启动器优先 AHK v2 明文脚本，且保留 exe 回退。"""
    text = _read_source("Goldenhandmaidens.py")
    assert "def _resolve_clicker_launcher" in text
    assert "AutoHotkey64.exe" in text
    assert 'get_resource_path("click_from_file.exe")' in text


@pytest.mark.parametrize("module_name", ["push", "hongbaolingqu"])
def test_popup_guard_present(module_name):
    """推图 / 红点领取必须有意外弹框的兜底处理。"""
    text = _read_source(f"{module_name}.py")
    assert "2026-11-10" in text
    assert "dianjikongbaichuguanbi" in text or "_unconfirmed_subitems" in text


# ---------- 跳转型点击必须校验界面（2026-11-10 第二轮） ----------

def test_click_and_confirm_reclicks_until_confirmed(monkeypatch):
    """点一次没生效就补点；补点后才成立要返回 True，两次都不成立返回 False。"""
    import types

    import common

    clicks = []
    monkeypatch.setattr(common, "find_center_silent", lambda *a, **k: (10, 20))
    monkeypatch.setattr(common, "click_position", lambda pos, **k: clicks.append(pos))
    monkeypatch.setattr(common, "time", types.SimpleNamespace(time=time.time,
                                                              sleep=lambda _s: None))

    # 第二次点击后才算进入目标界面
    ok = common.click_and_confirm(
        "tpl.png", "入口", lambda: len(clicks) >= 2,
        attempts=2, confirm_timeout=0.01,
    )
    assert ok is True
    assert len(clicks) == 2, "首次点击未生效时必须补点一次"

    clicks.clear()
    assert common.click_and_confirm(
        "tpl.png", "入口", lambda: False, attempts=2, confirm_timeout=0.01,
    ) is False
    assert len(clicks) == 2, "补点上限必须受 attempts 约束"


def test_friend_reclicks_social_when_panel_missing(monkeypatch):
    """点「社交」后好友面板没出现时必须补点，而不是直接判「未检测到一键赠礼」终止。"""
    names = []
    panel_states = [False, True]

    monkeypatch.setattr(haoyoujiangli, "wait_and_click",
                        lambda path, name, *a, **k: (names.append(name), True)[1])
    monkeypatch.setattr(haoyoujiangli, "_wait_friends_panel",
                        lambda timeout=0: panel_states.pop(0) if panel_states else True)
    monkeypatch.setattr(haoyoujiangli.time, "sleep", lambda _s: None)

    assert haoyoujiangli._enter_friends_panel() is True
    assert names[:3] == ["菜单", "社交(1)", "社交(2)"], names


def test_friend_falls_back_to_hud_when_social_never_opens(monkeypatch):
    """菜单→社交 始终进不去时要走主界面好友图标兜底，而不是直接失败。"""
    monkeypatch.setattr(haoyoujiangli, "wait_and_click", lambda *a, **k: True)
    monkeypatch.setattr(haoyoujiangli, "_wait_friends_panel", lambda timeout=0: False)
    monkeypatch.setattr(haoyoujiangli.time, "sleep", lambda _s: None)
    monkeypatch.setattr(haoyoujiangli, "_open_friends_via_hud", lambda *a, **k: True)

    assert haoyoujiangli._enter_friends_panel() is True


def test_push_clears_popup_without_close_hint(monkeypatch):
    """「已达成玩家」面板没有「点击空白处关闭」提示，靠左下 exit 箭头关掉。

    误点保护：备战界面有 autocha、或正处在极限门票弹窗时，绝不能点 exit。
    """
    import push

    visible = {push.tpl_exit}
    monkeypatch.setattr(
        push, "find_center_silent",
        lambda tpl, *a, **k: (1, 1) if tpl in visible else None,
    )
    clicked = []
    monkeypatch.setattr(
        push, "wait_and_click",
        lambda tpl, name, *a, **k: (clicked.append(name), True)[1],
    )

    flow = push.PushFlow(mode="normal", claim_first_clear=False)
    assert flow._clear_occluder() is True
    assert clicked == ["exit(遮挡面板)"]

    for guard in (push.tpl_autocha, push.tpl_guajijixian):
        clicked.clear()
        visible.clear()
        visible.add(push.tpl_exit)
        visible.add(guard)
        assert flow._clear_occluder() is False, "备战界面/极限弹窗下不得点 exit 退出"
        assert clicked == []

