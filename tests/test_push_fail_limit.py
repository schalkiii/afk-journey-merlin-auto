"""推图连续失败上限：达到配置次数后结束流程，成功推进（end）后清零。"""
import push


def _make_flow(monkeypatch, max_failures=2):
    flow = push.PushFlow(max_consecutive_failures=max_failures)
    monkeypatch.setattr(push, "wait_and_click", lambda *args, **kwargs: True)
    monkeypatch.setattr(flow, "_wait_for_any_state", lambda *args, **kwargs: push.tpl_autocha)
    monkeypatch.setattr(flow, "_wait_for_entry", lambda *args, **kwargs: True)
    return flow


def test_fail_limit_exits_and_sets_reason(monkeypatch):
    flow = _make_flow(monkeypatch, max_failures=2)

    # 第一次失败：未到上限，继续用当前阵容重试
    assert flow._st_on_fail() == push.STATE_START_BATTLE
    assert flow.consecutive_failures == 1
    assert flow.stop_reason == ""

    # 第二次失败：达到上限，转入退出状态并记录原因
    assert flow._st_on_fail() == push.STATE_EXIT
    assert flow.consecutive_failures == 2
    assert flow.stop_reason == "fail_limit"


def test_success_resets_failure_counter(monkeypatch):
    flow = _make_flow(monkeypatch, max_failures=3)
    flow.consecutive_failures = 2

    assert flow._st_on_end() == push.STATE_NEED_ENTRY
    assert flow.consecutive_failures == 0
