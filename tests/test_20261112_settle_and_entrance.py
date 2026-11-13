"""2026-11-12 实机回归：巅峰竞技场「跳过」后空转 180 秒 + 愿望单入口只搜 5 秒就放弃。

负验证留痕（把对应修复改回去，下列用例必须失败）：
- `dianfengjingjichang._settle_after_skip` 去掉「跳过按钮还在就补点」→
  `test_settle_reclicks_skip_while_battle_continues` 必须失败；
- 去掉「连续 N 轮无进度就提前放弃并留现场」→
  `test_settle_gives_up_after_stall_limit` 必须失败（会一直轮询到超时）；
- `_wait_for_any` 的 `quiet` 不生效 → `test_wait_for_any_quiet_does_not_log` 必须失败；
- `jieshezhanxian` 把日志改回「剩余扫荡次数已用完」→
  `test_guild_sweep_log_not_misleading` 必须失败；
- `yuanwangdan._ensure_panel` 改回「没有返回箭头就立刻 break」→
  `test_wishlist_entry_search_keeps_trying_without_back_arrow` 必须失败。
"""
import os
from pathlib import Path

import dianfengjingjichang as df
import yuanwangdan

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_source(relative_path):
    return (Path(ROOT) / relative_path).read_text(encoding="utf-8")


# ---------- 跳过之后：必须每一轮都有实质动作 ----------

def test_settle_reclicks_skip_while_battle_continues(monkeypatch):
    """跳过被吞、战斗还在打时，必须重新点跳过，而不是干等 180 秒。"""
    clicks = []
    monkeypatch.setattr(df, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(df, "check_stop", lambda: None)
    monkeypatch.setattr(df, "click_position", lambda pos, **_k: clicks.append(pos))
    # fail / jixutiaozhan 永不出现
    monkeypatch.setattr(df, "_wait_for_any", lambda *_a, **_k: None)
    # 跳过按钮始终可见 → 战斗仍在进行
    monkeypatch.setattr(df, "find_center_silent", lambda *_a, **_k: (1344, 765))
    monkeypatch.setattr(df, "dismiss_popup_away_from", lambda: None)
    monkeypatch.setattr(df, "is_loading_screen", lambda: False)

    # 第 3 轮时战斗结束（跳过消失）→ 走「无进度」分支累计到上限退出
    state = {"round": 0}

    def fake_find(template_path, *_a, **_k):
        if template_path == df.tpl_tiaoguo:
            state["round"] += 1
            return (1344, 765) if state["round"] <= 2 else None
        return None

    monkeypatch.setattr(df, "find_center_silent", fake_find)

    assert df._settle_after_skip((1344, 765)) is None
    assert clicks == [(1344, 765), (1344, 765)], "跳过还在就必须补点，且只补到它消失为止"


def test_settle_gives_up_after_stall_limit(monkeypatch):
    """完全认不出的界面：必须在 OUTCOME_STALL_LIMIT 轮后放弃并留现场，不得把 180 秒耗光。"""
    polls = []
    saved = []
    monkeypatch.setattr(df, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(df, "check_stop", lambda: None)

    def fake_wait(*_a, **_k):
        polls.append(1)

    monkeypatch.setattr(df, "_wait_for_any", fake_wait)
    monkeypatch.setattr(df, "find_center_silent", lambda *_a, **_k: None)
    monkeypatch.setattr(df, "is_loading_screen", lambda: False)
    monkeypatch.setattr(df, "capture_failure_context",
                        lambda *a, **_k: saved.append(a))

    assert df._settle_after_skip((1, 2)) is None
    assert len(polls) == df.OUTCOME_STALL_LIMIT, "只允许空转 OUTCOME_STALL_LIMIT 轮"
    assert saved, "放弃前必须保存失败现场，否则下次无法定位"


def test_settle_dismisses_known_popup_instead_of_waiting(monkeypatch):
    """命中「点击空白处关闭」时必须关弹窗，而不是当成无进展。"""
    dismissed = []
    rounds = {"n": 0}

    monkeypatch.setattr(df, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(df, "check_stop", lambda: None)
    monkeypatch.setattr(df, "_wait_for_any", lambda *_a, **_k: None)
    monkeypatch.setattr(df, "dismiss_popup_away_from", lambda: dismissed.append(1))
    monkeypatch.setattr(df, "is_loading_screen", lambda: False)

    def fake_find(template_path, *_a, **_k):
        rounds["n"] += 1
        if rounds["n"] >= 3:
            return None
        return (1129, 902) if "dianjikongbaichuguanbi" in template_path else None

    monkeypatch.setattr(df, "find_center_silent", fake_find)
    monkeypatch.setattr(df, "capture_failure_context", lambda *a, **_k: None)

    df._settle_after_skip((1, 2))
    assert dismissed, "提示模板命中时必须调用 dismiss_popup_away_from"


def test_wait_for_any_quiet_does_not_log(monkeypatch):
    """轮询循环里的超时不应该逐条打日志（今天刷出 36 条同样的行）。"""
    lines = []
    monkeypatch.setattr(df, "log", lambda msg, *_a, **_k: lines.append(msg))
    monkeypatch.setattr(df, "find_center_silent", lambda *_a, **_k: None)
    monkeypatch.setattr(df.time, "sleep", lambda _s: None)

    assert df._wait_for_any([(df.tpl_fail, "fail")], timeout=0.01, quiet=True) is None
    assert lines == [], "quiet=True 时不能打「放弃等待」"

    assert df._wait_for_any([(df.tpl_fail, "fail")], timeout=0.01) is None
    assert lines, "默认仍要打日志，否则交互式排查看不到等待过程"


# ---------- 结社战线：日志不能把「扫完」写成「没扫」 ----------

def test_guild_sweep_log_not_misleading():
    text = _read_source("jieshezhanxian.py")
    assert "扫荡完成，当日剩余次数已清零" in text
    assert 'log("【结社战线】剩余扫荡次数已用完")' not in text, (
        "这句紧跟在「本场失败」后面，读起来像「没扫就没了」，2026-11-11 已被用户误读"
    )


# ---------- 愿望单入口：不能搜 5 秒就放弃 ----------

def test_wishlist_entry_search_keeps_trying_without_back_arrow(monkeypatch):
    """找不到返回箭头也要搜满 3 轮：入口是场景立牌，镜头没带到时会整块缺席。"""
    searches = {"n": 0}
    logs = []

    monkeypatch.setattr(yuanwangdan, "log", lambda msg, *_a, **_k: logs.append(msg))
    monkeypatch.setattr(yuanwangdan, "check_stop", lambda: None)
    monkeypatch.setattr(yuanwangdan, "at_main_interface", lambda: True)
    monkeypatch.setattr(yuanwangdan.time, "sleep", lambda _s: None)
    monkeypatch.setattr(yuanwangdan, "_click_once", lambda *_a, **_k: None)
    monkeypatch.setattr(yuanwangdan, "_close_by_blank_hint", lambda: None)

    def fake_find(template_path, *_a, **_k):
        # 入口、一键选择、交付、结算、关弹窗模板全部不可见；返回箭头也不可见
        if template_path == yuanwangdan.tpl_entry:
            searches["n"] += 1

    monkeypatch.setattr(yuanwangdan, "_find", fake_find)
    # 本用例只关心「搜几轮」，把「点家园入口」这条路短路掉（它有自己的用例）
    monkeypatch.setattr(yuanwangdan, "_enter_homestead", lambda: False)

    assert yuanwangdan._ensure_panel() is False
    assert searches["n"] >= 3, "必须有 3 轮搜索，不能一次没找到就 break"
    assert any("3 轮" in msg for msg in logs), "放弃时要说清搜了几轮"


# ---------- 愿望单入口只在家园视图里：主界面必须先点「家园」 ----------

def test_ensure_panel_enters_homestead_from_main(monkeypatch):
    """在主界面直接找愿望单立牌永远找不到，必须点右下角「家园」入口进家园。"""
    state = {"in_homestead": False, "clicked_entry": False}

    def fake_find(template_path, *_a, **_k):
        if template_path == yuanwangdan.tpl_one_key:
            return (100, 200) if state["clicked_entry"] else None
        if template_path == yuanwangdan.tpl_entry:
            return (38, 566) if state["in_homestead"] else None
        return None

    def fake_enter_homestead():
        state["in_homestead"] = True
        return True

    def fake_click_once(_pos, *_a, **_k):
        state["clicked_entry"] = True     # 只有进了家园才点得到立牌

    monkeypatch.setattr(yuanwangdan, "_find", fake_find)
    monkeypatch.setattr(yuanwangdan, "_enter_homestead", fake_enter_homestead)
    monkeypatch.setattr(yuanwangdan, "_click_once", fake_click_once)
    monkeypatch.setattr(yuanwangdan, "_close_by_blank_hint", lambda: None)
    monkeypatch.setattr(yuanwangdan, "log", lambda *_a, **_k: None)
    monkeypatch.setattr(yuanwangdan.time, "sleep", lambda _s: None)

    assert yuanwangdan._ensure_panel() is True
    assert state["in_homestead"] and state["clicked_entry"]


def test_enter_homestead_uses_click_and_confirm(monkeypatch):
    """入口跳转必须走 click_and_confirm：裸点击被窗口激活吞掉就会一路错下去。"""
    captured = {}

    def fake_click_and_confirm(template_path, name, confirm, **kwargs):
        captured["tpl"] = template_path
        captured["name"] = name
        captured["confirm"] = confirm()
        return True

    monkeypatch.setattr(yuanwangdan, "click_and_confirm", fake_click_and_confirm)
    monkeypatch.setattr(yuanwangdan, "_find", lambda *_a, **_k: (38, 566))

    assert yuanwangdan._enter_homestead() is True
    assert captured["tpl"] == yuanwangdan.tpl_jiayuan
    assert "家园" in captured["name"]
    assert captured["confirm"] is True, "confirm 应判愿望单立牌是否出现"
