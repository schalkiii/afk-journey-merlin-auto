"""红点领取模块：领取循环的计数、停止条件与上限保护。"""
import hongbaolingqu as hb


def test_claim_stops_when_nothing_left(monkeypatch):
    monkeypatch.setattr(hb, "wait_and_click", lambda *args, **kwargs: False)
    monkeypatch.setattr(hb, "find_center_silent", lambda *args, **kwargs: None)
    assert hb.claim_current_view() == 0


def test_claim_loop_uses_both_buttons_and_closes_popup(monkeypatch):
    """一键领取与单个领取混着出现时都要点到，且每次领取后都尝试关奖励弹窗。"""
    actions = []
    # 第 1 轮有一键领取，第 2 轮只剩单个领取，第 3 轮两者都没有
    yijian_results = iter([True, False, False])
    lingqu_results = iter([(1100, 400), None])

    def fake_wait_and_click(template_path, name, *args, **kwargs):
        if template_path == hb.tpl_yijianlingqu:
            return next(yijian_results)
        return False

    def fake_find(template_path, *args, **kwargs):
        if template_path == hb.tpl_blank_close:
            actions.append("close")
            return (100, 100)
        if template_path == hb.tpl_lingqu:
            return next(lingqu_results)
        return None

    monkeypatch.setattr(hb, "wait_and_click", fake_wait_and_click)
    monkeypatch.setattr(hb, "find_center_silent", fake_find)
    monkeypatch.setattr(hb, "click_blank_to_exit", lambda *args, **kwargs: actions.append("blank"))
    monkeypatch.setattr(hb, "click_position", lambda pos, **kwargs: actions.append(("click", pos)))

    assert hb.claim_current_view() == 2
    assert actions == [
        "close", "blank",
        ("click", (1100, 400)), "close", "blank",
    ]


def test_claim_loop_stops_at_cap(monkeypatch):
    """领取后界面不刷新时靠上限退出，不能死循环点同一个按钮。"""
    monkeypatch.setattr(hb, "wait_and_click", lambda *args, **kwargs: True)
    monkeypatch.setattr(hb, "find_center_silent", lambda *args, **kwargs: None)
    monkeypatch.setattr(hb, "click_blank_to_exit", lambda *args, **kwargs: None)
    assert hb.claim_current_view() == hb.MAX_CLAIM_PER_VIEW
