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


def test_flow_push_stop_reason_resets_even_if_start_fails(monkeypatch):
    """初始化/运行提前抛异常时不能残留上一轮的 fail_limit，否则循环推图会误停。"""
    import flow_push

    flow_push.LAST_STOP_REASON = "fail_limit"

    def _raise(*args, **kwargs):
        raise RuntimeError("start failed")

    monkeypatch.setattr(flow_push, "_push_flow", _raise)
    try:
        flow_push.flow_push_mode1()
    except RuntimeError:
        pass
    assert flow_push.LAST_STOP_REASON == ""

    push.LAST_STOP_REASON = "fail_limit"

    def _raise_init():
        raise RuntimeError("init failed")

    monkeypatch.setattr(push, "init_templates_from_dir", _raise_init)
    try:
        push.flow_push_mode1()
    except RuntimeError:
        pass
    assert push.LAST_STOP_REASON == ""
