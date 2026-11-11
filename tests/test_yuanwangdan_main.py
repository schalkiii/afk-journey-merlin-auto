"""家园愿望单 `main()` 主状态机（交付循环 / 领奖时机 / 卡死退出 / 收尾清理）。

全部在模块级接缝打桩，不接触真实游戏。负验证留痕：
- 删掉 `claim_due` 只在交付后置位的逻辑（改成每轮都试），
  `test_main_tries_claim_only_at_start_and_after_delivery` 必须失败；
- 把 idle 上限判断去掉，`test_main_exits_after_idle_rounds` 必须失败；
- 把收尾的结算关闭循环删掉，`test_main_closes_leftover_result_dialog` 必须失败。
"""

import types

import pytest

import yuanwangdan as ywd


class _FakeTime:
    """让 main() 的等待不真的睡；同时提供 time() 以兼容其它被打桩函数。"""

    def __init__(self):
        self.elapsed = 0.0

    def sleep(self, seconds):
        self.elapsed += seconds

    def time(self):
        return self.elapsed


@pytest.fixture
def harness(monkeypatch):
    """统一打桩 main() 的全部外部依赖，返回可配置的记录对象。"""
    rec = types.SimpleNamespace(
        logs=[], clicks=[], clicks_once=[], close_hints=[], claim_calls=[],
        craft_calls=0, return_main_calls=0,
        claim_result=False, find_map={}, state_seq=None, state_holder=None,
    )

    monkeypatch.setattr(ywd, "MAX_ORDERS", 3)
    monkeypatch.setattr(ywd, "time", _FakeTime())
    monkeypatch.setattr(ywd, "log", lambda msg: rec.logs.append(msg))
    monkeypatch.setattr(ywd, "_ensure_panel", lambda: True)
    monkeypatch.setattr(ywd, "_click", lambda pos, wait=0: rec.clicks.append(pos))
    monkeypatch.setattr(ywd, "_click_once", lambda pos, wait=0: rec.clicks_once.append(pos))
    monkeypatch.setattr(ywd, "_close_by_blank_hint", lambda: rec.close_hints.append(True))
    monkeypatch.setattr(ywd, "_craft_from_lack", lambda: (setattr(rec, "craft_calls", rec.craft_calls + 1), True)[1])
    monkeypatch.setattr(ywd, "flow_return_main", lambda: setattr(rec, "return_main_calls", rec.return_main_calls + 1))

    def fake_claim(label_pos):
        rec.claim_calls.append(label_pos)
        return rec.claim_result

    monkeypatch.setattr(ywd, "_claim_reward", fake_claim)

    def fake_find(template_path, *args, **kwargs):
        return rec.find_map.get(template_path)

    monkeypatch.setattr(ywd, "_find", fake_find)

    def fake_panel_state():
        if rec.state_seq is not None:
            if rec.state_seq:
                return rec.state_seq.pop(0)
            return None, None
        return rec.state_holder or (None, None)

    monkeypatch.setattr(ywd, "_panel_state", fake_panel_state)
    rec.monkeypatch = monkeypatch
    return rec


def test_main_delivers_until_max_orders(harness):
    harness.state_holder = (ywd.STATE_DELIVER, (3000, 800))

    assert ywd.main() is True
    assert len(harness.clicks) == 3, "三单交付应各点一次「交付」"
    assert any("交付 3 单" in line for line in harness.logs)
    assert harness.return_main_calls == 1


def test_main_tries_claim_only_at_start_and_after_delivery(harness):
    """领奖只在开局与每次交付后尝试；连续待选状态不得每轮白点礼盒。"""
    harness.find_map[ywd.tpl_label] = (295, 125)
    harness.state_holder = (ywd.STATE_ONE_KEY, (3010, 810))

    ywd.main()
    assert len(harness.claim_calls) == 1, "没有交付就不该再次试领"


def test_main_counts_successful_claim(harness):
    harness.find_map[ywd.tpl_label] = (295, 125)
    harness.claim_result = True
    harness.state_holder = (ywd.STATE_DELIVER, (3000, 800))

    assert ywd.main() is True
    assert any("领取奖励 3 次" in line for line in harness.logs)


def test_main_exits_after_idle_rounds(harness):
    harness.state_holder = (ywd.STATE_ONE_KEY, (3010, 810))

    assert ywd.main() is False
    assert any("判定卡死" in line for line in harness.logs)
    assert harness.clicks_once, "ONE_KEY 状态应尝试点击一键选择"


def test_main_closes_leftover_result_dialog(harness):
    harness.state_holder = (ywd.STATE_DELIVER, (3000, 800))
    harness.find_map[ywd.tpl_result] = (2600, 200)
    harness.find_map[ywd.tpl_entry] = (100, 100)

    assert ywd.main() is True
    assert harness.close_hints, "收尾必须关掉最后一单留下的结算弹窗"
    assert harness.return_main_calls == 0, "仍在愿望单入口可见时不该空跑 recover"


def test_main_stops_when_craft_budget_exhausted(harness):
    harness.monkeypatch.setattr(ywd, "MAX_CRAFTS", 1)
    harness.state_holder = (ywd.STATE_LACK, (2800, 400))
    assert ywd.main() is False
    assert harness.craft_calls == 1
    assert any("已达单次制作上限" in line for line in harness.logs)
