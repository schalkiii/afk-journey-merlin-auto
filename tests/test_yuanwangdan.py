"""家园愿望单：状态判定优先级、模板消失等待语义、领奖偏移兜底（不接触真实游戏）。

实测依据（见 yuanwangdan.py 模块 docstring）：
- 结算标题带流光动画，同一模板连续帧匹配分在 0.82–0.95 抖动，所以结算排在判定顺序最后，
  并且只靠「点击空白处关闭」提示兜底；弹窗压住面板时面板按钮只会匹配到 0.43–0.50。
- 进度礼盒只有第一档（金色心形）能被模板整档命中，其它档位（青色宝石）外观不同跨不了档，
  必须退回「愿望单标题锚点 + GIFT_CLICK_OFFSET」——这条兜底线上线后天天在跑。
- 领奖礼盒是弹窗类按钮，必须单击：连点的第二次会把刚弹出的「获得奖励」当场关掉，
  表现为奖励已发但流程判「未领取」（2026-11-07 实机踩过）。
"""
import types

import pytest

import yuanwangdan as ywd

# 每个模板给一个互不相同的坐标：这样断言锚点才能证明返回的是「该状态自己的」命中点，
# 而不是随便某个命中点。
TEMPLATE_POS = {
    ywd.tpl_claim: (3200, 700),
    ywd.tpl_lack: (2800, 400),
    ywd.tpl_deliver: (3000, 800),
    ywd.tpl_one_key: (3010, 810),
    ywd.tpl_result: (2600, 200),
    ywd.tpl_close_popup: (2800, 860),
}


def _stub_panel_find(monkeypatch, present):
    """桩掉 _find：present 为「画面上能匹配到的模板」集合，返回模板探测顺序。

    探测顺序本身就是被测逻辑的一部分（结算必须最后探、且只在前四态都排除后才兜底），
    所以把每次 _find 的模板都记下来供断言。
    """
    probes = []

    def fake_find(template_path, *args, **kwargs):
        probes.append(template_path)
        return TEMPLATE_POS[template_path] if template_path in present else None

    monkeypatch.setattr(ywd, "_find", fake_find)
    return probes


# (画面中出现的模板, 期望状态, 期望锚点来源模板；None 表示锚点必须为 None)
PANEL_STATE_CASES = [
    # 五态同时可见时按 领奖 > 不足 > 交付 > 一键 > 结算 依次压过
    ({ywd.tpl_claim, ywd.tpl_lack, ywd.tpl_deliver, ywd.tpl_one_key, ywd.tpl_result},
     ywd.STATE_CLAIM, ywd.tpl_claim),
    ({ywd.tpl_lack, ywd.tpl_deliver, ywd.tpl_one_key, ywd.tpl_result},
     ywd.STATE_LACK, ywd.tpl_lack),
    ({ywd.tpl_deliver, ywd.tpl_one_key, ywd.tpl_result},
     ywd.STATE_DELIVER, ywd.tpl_deliver),
    ({ywd.tpl_one_key, ywd.tpl_result},
     ywd.STATE_ONE_KEY, ywd.tpl_one_key),
    # 只有结算标题（流光动画刚好匹配上的那一帧）
    ({ywd.tpl_result}, ywd.STATE_RESULT, None),
    # 只有「点击空白处关闭」提示、结算标题漏判：兜底分支，本模块全部设计动机所在
    ({ywd.tpl_close_popup}, ywd.STATE_RESULT, None),
    # 兜底提示不得越过强判据：不足弹框盖在面板上时同样带着该提示
    ({ywd.tpl_lack, ywd.tpl_close_popup}, ywd.STATE_LACK, ywd.tpl_lack),
    ({ywd.tpl_claim, ywd.tpl_close_popup}, ywd.STATE_CLAIM, ywd.tpl_claim),
    ({}, None, None),
]


@pytest.mark.parametrize("present, expected_state, anchor_template",
                         PANEL_STATE_CASES,
                         ids=[f"{index + 1}-{case[1] or 'unknown'}"
                              for index, case in enumerate(PANEL_STATE_CASES)])
def test_panel_state_priority(monkeypatch, present, expected_state, anchor_template):
    """判定顺序：领奖 > 不足弹框 > 交付 > 一键选择 > 结算；结算靠关闭提示兜底且不带锚点。"""
    _stub_panel_find(monkeypatch, present)

    state, anchor = ywd._panel_state()

    assert state == expected_state
    assert anchor == (TEMPLATE_POS[anchor_template] if anchor_template else None)


def test_panel_state_stops_probing_at_first_hit(monkeypatch):
    """命中即返回：前面几态探完就不再往下探，探测顺序本身就是判定优先级。"""
    probes = _stub_panel_find(monkeypatch, {ywd.tpl_claim, ywd.tpl_lack, ywd.tpl_deliver})

    assert ywd._panel_state() == (ywd.STATE_CLAIM, TEMPLATE_POS[ywd.tpl_claim])
    assert probes == [ywd.tpl_claim]


def test_panel_state_result_hit_skips_close_hint_probe(monkeypatch):
    """结算标题命中时不必再探关闭提示，但前四态必须先探完才轮到结算。"""
    probes = _stub_panel_find(monkeypatch, {ywd.tpl_result})

    assert ywd._panel_state() == (ywd.STATE_RESULT, None)
    assert probes == [ywd.tpl_claim, ywd.tpl_lack, ywd.tpl_deliver, ywd.tpl_one_key,
                      ywd.tpl_result]


class _FakeTime:
    """假时钟：每次 time() 推进 step 秒，sleep 只记账不真等（测试绝不挂住）。"""

    def __init__(self, step=1.0):
        self.now = 0.0
        self.step = step
        self.slept = []

    def time(self):
        value = self.now
        self.now += self.step
        return value

    def sleep(self, seconds):
        self.slept.append(seconds)


def _stub_wait(monkeypatch, present_sequence, step=1.0):
    """桩掉 _wait_gone 的三条外部接缝：时钟、check_stop、_find；返回调用记账。

    present_sequence 逐次给出「模板是否还在画面上」，用完后按最后一项保持，
    于是循环轮数只由 timeout 决定，便于断言 _find 被调了几次。
    """
    fake_time = _FakeTime(step)
    record = {"find": 0, "stop": 0}

    def fake_find(template_path, *args, **kwargs):
        index = record["find"]
        record["find"] += 1
        present = (present_sequence[index]
                   if index < len(present_sequence) else present_sequence[-1])
        return (500, 500) if present else None

    def fake_check_stop():
        record["stop"] += 1

    monkeypatch.setattr(ywd, "time",
                        types.SimpleNamespace(time=fake_time.time, sleep=fake_time.sleep))
    monkeypatch.setattr(ywd, "_find", fake_find)
    monkeypatch.setattr(ywd, "check_stop", fake_check_stop)
    return record, fake_time


def test_wait_gone_returns_true_when_template_disappears(monkeypatch):
    """模板中途消失即立刻返回 True，不再继续轮询到超时。"""
    # timeout=3 + 每秒推进 1：循环体最多 2 轮，第 2 轮模板消失
    record, fake_time = _stub_wait(monkeypatch, [True, False])

    assert ywd._wait_gone(ywd.tpl_lack, 3) is True
    assert record["find"] == 2, "消失当轮就该返回，不能再多探一次"
    assert record["stop"] == 2
    assert fake_time.slept == [0.5]


def test_wait_gone_times_out_and_rechecks_at_deadline(monkeypatch):
    """timeout 内始终没消失时返回 False，且到期后还要再确认最后一次。"""
    record, fake_time = _stub_wait(monkeypatch, [True])

    assert ywd._wait_gone(ywd.tpl_lack, 3) is False
    assert record["find"] == 3, "两轮轮询之外，函数尾部还必须再查一次"
    assert fake_time.slept == [0.5, 0.5]


def test_wait_gone_zero_timeout_still_checks_once(monkeypatch):
    """timeout=0 时循环体一次都不进，但尾部仍要「最后一刻再确认」一次。

    这保证 _wait_gone(t, 0) 等价于「现在是否已消失」，而不是无脑返回 True。
    """
    record, fake_time = _stub_wait(monkeypatch, [False])

    assert ywd._wait_gone(ywd.tpl_lack, 0) is True
    assert record["find"] == 1
    assert record["stop"] == 0, "timeout=0 不该进入轮询循环"
    assert fake_time.slept == []


def test_wait_gone_zero_timeout_false_when_still_present(monkeypatch):
    """timeout=0 且模板仍在时必须判 False，否则制作中「按钮未消失」会被误判成已完成。"""
    record, _fake_time = _stub_wait(monkeypatch, [True])

    assert ywd._wait_gone(ywd.tpl_lack, 0) is False
    assert record["find"] == 1
    assert record["stop"] == 0


# 礼盒命中点与「标题 + 偏移」兜底点必须取不同坐标，否则两条分支互换也测不出来
GIFT_HIT_POS = (3054, 178)
LABEL_POS = (2418, 131)


def _stub_claim(monkeypatch, gift_pos, claim_pos):
    """桩掉领奖的接缝：_find（礼盒 / 领奖标题）、_click、关闭弹窗；返回各自的调用记账。"""
    clicks, closes, lookups = [], [], []

    def fake_find(template_path, *args, **kwargs):
        lookups.append((template_path, dict(kwargs)))
        if template_path == ywd.tpl_gift:
            return gift_pos
        if template_path == ywd.tpl_claim:
            return claim_pos
        return None

    monkeypatch.setattr(ywd, "_find", fake_find)
    monkeypatch.setattr(ywd, "_click_once", lambda pos, wait=None: clicks.append((pos, wait)))
    monkeypatch.setattr(ywd, "_close_by_blank_hint", lambda: closes.append("close"))
    monkeypatch.setattr(ywd, "log", lambda *args, **kwargs: None)
    return clicks, closes, lookups


def test_claim_reward_clicks_gift_template_when_it_hits(monkeypatch):
    """第一档金色心形可整档命中：直接点模板命中坐标，不叠加偏移。"""
    clicks, closes, lookups = _stub_claim(monkeypatch, GIFT_HIT_POS, (3200, 700))

    assert ywd._claim_reward(LABEL_POS) is True
    assert clicks == [(GIFT_HIT_POS, 0.6)]
    assert lookups[0] == (ywd.tpl_gift, {"threshold": ywd.GIFT_THRESHOLD})
    assert closes == ["close"]


def test_claim_reward_falls_back_to_label_offset(monkeypatch):
    """其它档位（青色宝石）模板跨不了档：退回「标题锚点 + GIFT_CLICK_OFFSET」。

    坐标按 2026-11-07 实机重测结果写死（礼盒 486,56 / 标题 418,31，偏移 (68,25)）；
    旧的 (62,35) 落在礼盒边缘，进度奖励一直没被领到，故这里刻意不复用常量做断言。
    """
    clicks, closes, lookups = _stub_claim(monkeypatch, None, (3200, 700))

    assert ywd._claim_reward(LABEL_POS) is True
    assert clicks == [((2486, 156), 0.6)]
    assert lookups[0][0] == ywd.tpl_gift
    assert closes == ["close"]


def test_claim_reward_reports_failure_without_claim_popup(monkeypatch):
    """点了礼盒但「获得奖励」弹窗没出现（无可领档位）：补点一次后判未领取且不关弹窗。

    2026-11-08 实跑：无可领奖励时 3 次尝试白等 15 秒，已减为 2 次（首次可能被吞、
    第二次生效）；本用例钉住该次数，避免回退到 3 次。
    """
    clicks, closes, _lookups = _stub_claim(monkeypatch, None, None)

    assert ywd._claim_reward(LABEL_POS) is False
    assert clicks == [((2486, 156), 0.6)] * 2
    assert closes == []


# 旧版「愿望单需求」标签中心 → 同一卡片「选择」按钮中心的偏移。改动后常量与点击都已删除，
# 这里刻意写死旧值，用来证明流程不会再点开制作配方。
OLD_WISH_SELECT_OFFSET_Y = 157
ARROW_POS = (2000, 500)
WISH_LABEL_POS = (2400, 300)
COOK_POS = (2896, 859)


def test_craft_from_lack_skips_product_card_and_starts_quantity(monkeypatch):
    """补货流程只确认生产界面并选次数，不再点「愿望单需求」产品卡片打开配方。"""
    clicks = []
    find_calls = []
    start_button_calls = []

    def fake_find(template_path, *args, **kwargs):
        find_calls.append((template_path, args, dict(kwargs)))
        if template_path == ywd.tpl_path_arrow:
            return ARROW_POS
        if template_path == ywd.tpl_wish_label:
            return WISH_LABEL_POS
        if template_path == ywd.tpl_lack:
            return None
        # 制作完成后「开始」按钮重新出现
        return COOK_POS

    def fake_find_start_button(timeout=0):
        start_button_calls.append(timeout)
        if len(start_button_calls) == 1:
            return None, None
        return ywd.tpl_cook, COOK_POS

    def fake_click_position(pos, wait=None, twice=True):
        clicks.append((pos, wait, twice))

    fake_clock = _FakeTime()

    monkeypatch.setattr(ywd, "_find", fake_find)
    monkeypatch.setattr(ywd, "_find_start_button", fake_find_start_button)
    monkeypatch.setattr(ywd, "click_position", fake_click_position)
    monkeypatch.setattr(ywd, "_wait_gone", lambda template_path, timeout: True)
    monkeypatch.setattr(ywd, "_back_to_homestead", lambda: True)
    monkeypatch.setattr(ywd, "_ensure_panel", lambda: True)
    monkeypatch.setattr(ywd, "game_client_region", lambda refresh=False: None)
    monkeypatch.setattr(ywd, "check_stop", lambda: None)
    monkeypatch.setattr(ywd, "log", lambda *args, **kwargs: None)
    monkeypatch.setattr(ywd, "time",
                        types.SimpleNamespace(time=fake_clock.time, sleep=fake_clock.sleep))

    assert ywd._craft_from_lack() is True

    # 第一次循环未见到开始按钮、愿望单需求标签命中；第二次才拿到开始按钮
    assert len(start_button_calls) == 2
    assert any(template_path == ywd.tpl_wish_label and kwargs == {"timeout": 0.85}
               for template_path, _args, kwargs in find_calls), "标签仍须保留用于确认生产界面"

    qty_pos = (COOK_POS[0] + ywd.QTY_BUTTON_OFFSET[0],
               COOK_POS[1] + ywd.QTY_BUTTON_OFFSET[1])
    old_card_select_pos = (WISH_LABEL_POS[0], WISH_LABEL_POS[1] + OLD_WISH_SELECT_OFFSET_Y)
    assert clicks == [
        (ARROW_POS, 1.0, False),
        (qty_pos, 1.0, False),
        (qty_pos, 1.0, False),
        (COOK_POS, 1.0, False),
    ]
    assert old_card_select_pos not in [pos for pos, _wait, _twice in clicks], \
        "点产品卡片会打开制作配方，补货流程不应出现该点击"
