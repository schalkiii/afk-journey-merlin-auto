"""推图连续失败上限：达到配置次数后结束流程，成功推进（end）后清零。"""
import push


def _make_flow(monkeypatch, max_failures=2):
    flow = push.PushFlow(max_consecutive_failures=max_failures)
    monkeypatch.setattr(push, "wait_and_click", lambda *args, **kwargs: True)
    monkeypatch.setattr(push, "find_center_silent", lambda *args, **kwargs: None)
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


def test_end_result_page_click_swallowed_falls_back_to_back_arrow(monkeypatch):
    """end(k) 首次点击被吞（结果页仍在）时，用返回箭头退出结果页再确认模式入口。"""
    flow = push.PushFlow(max_consecutive_failures=5)
    clicked = []

    def _fake_click(template_path, action_name, *args, **kwargs):
        clicked.append(action_name)
        return True

    # 第一次等入口超时（还在结果页），兜底返回箭头后才出现入口
    entry_results = iter([None, "entry.png"])
    monkeypatch.setattr(push, "wait_and_click", _fake_click)
    monkeypatch.setattr(push, "find_center_silent", lambda *args, **kwargs: (800, 225))
    monkeypatch.setattr(flow, "_wait_for_entry", lambda *args, **kwargs: next(entry_results))

    assert flow._st_on_end() == push.STATE_NEED_ENTRY
    assert clicked == ["end(k)_click", "exit(j)_end"]
    assert flow.consecutive_failures == 0


def test_end_gives_up_when_result_page_already_left(monkeypatch):
    """确认失败但结果页已经消失时不再盲点返回箭头，直接结束本轮，避免点到别的界面。"""
    flow = push.PushFlow(max_consecutive_failures=5)
    clicked = []

    def _fake_click(template_path, action_name, *args, **kwargs):
        clicked.append(action_name)
        return True

    monkeypatch.setattr(push, "wait_and_click", _fake_click)
    monkeypatch.setattr(push, "find_center_silent", lambda *args, **kwargs: None)
    monkeypatch.setattr(flow, "_wait_for_entry", lambda *args, **kwargs: None)

    assert flow._st_on_end() == push.STATE_DONE
    assert clicked == ["end(k)_click"]
    assert flow.finished_ok is False


def test_repeat_click_swallowed_is_retried(monkeypatch):
    """首次 repeat(e) 被窗口激活吞掉（仍停在失败页）时补点一次，而不是直接结束本轮推图。"""
    flow = push.PushFlow(max_consecutive_failures=5)
    clicked = []

    def _fake_click(template_path, action_name, *args, **kwargs):
        clicked.append(action_name)
        return True

    # 第一次确认超时，第二次确认回到推图界面
    confirm_results = iter([None, push.tpl_autocha])
    monkeypatch.setattr(push, "wait_and_click", _fake_click)
    monkeypatch.setattr(push, "find_center_silent", lambda *args, **kwargs: (100, 100))
    monkeypatch.setattr(flow, "_wait_for_any_state", lambda *args, **kwargs: next(confirm_results))

    assert flow._st_on_fail() == push.STATE_START_BATTLE
    assert clicked == ["repeat(e)(1)", "repeat(e)(2)"]


def test_repeat_not_retried_once_off_fail_page(monkeypatch):
    """确认失败但已经离开失败页时不能再盲点 repeat，否则会点到界面之外的位置。"""
    flow = push.PushFlow(max_consecutive_failures=5)
    clicked = []

    def _fake_click(template_path, action_name, *args, **kwargs):
        clicked.append(action_name)
        return True

    monkeypatch.setattr(push, "wait_and_click", _fake_click)
    monkeypatch.setattr(push, "find_center_silent", lambda *args, **kwargs: None)
    monkeypatch.setattr(flow, "_wait_for_any_state", lambda *args, **kwargs: None)

    assert flow._st_on_fail() == push.STATE_DONE
    assert clicked == ["repeat(e)(1)"]
    assert flow.finished_ok is False


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
