"""2026-11-20 实跑复盘的两条修复。

今天 20 项里 3 项 ✘，其中两项是「一次点击被吞就整轮判失败」：

1. 普竞（08:05:07）：点「战斗」没有生效，界面停在备战页整整 180 秒；失败现场里
   绿色「战斗」按钮仍是 0.991 分。旧实现只等不补点，把一次吞点击放大成 3 分半失败。
2. 推图（08:48:15）：面板还在「数据统计中」时点「一键采用」无效，旧实现一次点击
   等 10 秒没切页就直接结束整轮——此前已经推过多个关卡，进度全被记成 ✘。

（第三项巅峰竞技场 180 秒超时在 11-18 已改 300 秒，今天跑的是 11-17 的旧 exe。）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pujing
import push


class _FakeTime:
    """可控时钟：sleep 直接把当前时间往前推，用例不必真等 180 秒。"""

    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(float(seconds), 0.01)


def _stub_clock(monkeypatch):
    clock = _FakeTime()
    monkeypatch.setattr(pujing, "time", clock)
    monkeypatch.setattr(pujing, "check_stop", lambda *a, **k: None)
    return clock


def test_wait_battle_outcome_reclicks_when_battle_still_visible(monkeypatch):
    """「战斗」仍在屏上说明这一击被吞：补点后再等，信号出现即返回。"""
    clock = _stub_clock(monkeypatch)
    clicks = []
    polls = {"n": 0}

    def fake_wait_for_any(templates, **kwargs):
        polls["n"] += 1
        clock.now += pujing.OUTCOME_POLL
        if polls["n"] >= 2:
            return (pujing.tpl_pujingjieshu, "pujingjieshu", (900, 800))
        return None

    monkeypatch.setattr(pujing, "wait_for_any", fake_wait_for_any)
    monkeypatch.setattr(
        pujing, "find_center_silent",
        lambda path, *a, **k: (1161, 895) if path == pujing.tpl_zhandou else None,
    )
    monkeypatch.setattr(pujing, "send_coord", lambda x, y: clicks.append((x, y)))

    outcome = pujing._wait_battle_outcome()

    assert outcome[0] == pujing.tpl_pujingjieshu
    assert clicks == [(1161, 895)]


def test_wait_battle_outcome_caps_reclicks_then_times_out(monkeypatch):
    """补点有上限：一直没信号时最多补 BATTLE_CLICK_RETRY 次，然后按超时返回 None。"""
    _stub_clock(monkeypatch)
    clicks = []

    def fake_wait_for_any(templates, **kwargs):
        pujing.time.now += pujing.OUTCOME_POLL

    monkeypatch.setattr(pujing, "wait_for_any", fake_wait_for_any)
    monkeypatch.setattr(
        pujing, "find_center_silent",
        lambda path, *a, **k: (1161, 895) if path == pujing.tpl_zhandou else None,
    )
    monkeypatch.setattr(pujing, "send_coord", lambda x, y: clicks.append((x, y)))

    assert pujing._wait_battle_outcome() is None
    assert len(clicks) == pujing.BATTLE_CLICK_RETRY


def _stub_lineup_flow(monkeypatch, post_adopt_states):
    """构造一个停在「阵容可用」分支上的推图状态机。

    post_adopt_states 依次作为每次「一键采用」后的等待结果，用完后返回 None。
    """
    flow = push.PushFlow(mode="normal", skip_manual=False, claim_first_clear=False)
    names = []

    monkeypatch.setattr(push, "find_center_silent", lambda *a, **k: None)
    monkeypatch.setattr(push, "_load_warehouse_levels", dict)
    monkeypatch.setattr(push, "_recognize_lineup_with_levels", lambda: ([], None))
    monkeypatch.setattr(push, "_is_lineup_acceptable", lambda *a, **k: True)
    monkeypatch.setattr(push, "wait_and_click",
                        lambda path, name, *a, **k: names.append(name) or True)
    monkeypatch.setattr(
        flow, "_wait_for_any_state",
        lambda *a, **k: post_adopt_states.pop(0) if post_adopt_states else None,
    )
    return flow, names


def test_lineup_adopt_retries_swallowed_click(monkeypatch):
    """第一次点「一键采用」没反应时补点，第二次生效即继续开战。"""
    flow, names = _stub_lineup_flow(monkeypatch, [None, push.tpl_autocha])

    assert flow._st_lineup_select() == push.STATE_START_BATTLE
    assert names == ["oneclick(i) 采用阵容 0", "oneclick(i) 采用阵容 0(补点1)"]
    assert flow.have_lineup is True


def test_lineup_adopt_retries_exhausted_with_progress_ends_normally(monkeypatch):
    """补点仍无效，但本轮已推过关卡：按正常结束收尾，不再把 19 分钟工作记成失败。"""
    flow, _names = _stub_lineup_flow(monkeypatch, [])
    flow.stage_cleared = True

    assert flow._st_lineup_select() == push.STATE_DONE
    assert flow.finished_ok is True
    assert flow.stop_reason == "adopt_unconfirmed"


def test_lineup_adopt_retries_exhausted_without_progress_fails(monkeypatch):
    """一次都没推过关时，补点无效仍然是真失败。"""
    flow, _names = _stub_lineup_flow(monkeypatch, [])

    assert flow._st_lineup_select() == push.STATE_DONE
    assert flow.finished_ok is False
    assert flow.stop_reason == ""
