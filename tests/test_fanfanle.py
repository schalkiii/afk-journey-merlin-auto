"""翻翻乐模块：烧钥匙循环的计数与停止条件（不接触真实游戏）。

关键性质：一次点击会连抽到本轮 100 满，所以「钥匙余量 / 累计进度有没有变」是成败判据——
判据错了就会像最初那样把「已经推进」误读成「点了没反应」（2026-11-10 实机：钥匙 157→0
全烧完了，每一轮却都报「钥匙余量未变化」）。

2026-11-11 另一面：一轮点完有翻牌结算演出，演出期间再点不生效。旧实现把「点了没变化」
直接当成「钥匙已用完」，当天钥匙还剩 376 把就报「完成 1 轮、用完」。所以「没变化」现在
必须重试到 `CLICK_RETRIES` 次才允许下结论。
"""
import fanfanle as ff


def _patch_common(monkeypatch, button_pos=(1000, 750)):
    clicks = []
    monkeypatch.setattr(ff, "check_stop", lambda: None)
    monkeypatch.setattr(ff, "invalidate_screenshot_cache", lambda: None)
    monkeypatch.setattr(ff.time, "sleep", lambda _s: None)   # 轮间稳定等待不占测试时间
    # 只有「点击增加进度」按钮命中；「触发事件」选择页不在屏上
    monkeypatch.setattr(
        ff, "find_center_silent",
        lambda template_path, *args, **kwargs: (
            None if template_path == ff.tpl_trigger_event else button_pos
        ),
    )
    monkeypatch.setattr(ff, "click_position", lambda pos, **kwargs: clicks.append(pos))
    monkeypatch.setattr(ff, "_region_crop", lambda region: b"crop")
    return clicks


def test_burn_stops_when_keys_unchanged(monkeypatch):
    """钥匙余量不变＝没钥匙了，必须停；但要重试几次确认，不能一次就下结论。"""
    clicks = _patch_common(monkeypatch)
    monkeypatch.setattr(ff, "_wait_keys_change", lambda before_keys, before_progress, timeout=6.0: False)

    assert ff.burn_keys(5) == 0
    assert len(clicks) == ff.CLICK_RETRIES, (
        "结算演出期间点不动是常态，必须重试到 CLICK_RETRIES 次才判定钥匙用完"
    )


def test_burn_counts_every_round_that_consumes_keys(monkeypatch):
    """前两轮钥匙被烧掉要计数，第三轮起烧完（余量不变）重试若干次后停止。"""
    state = {"round": 0}

    def fake_change(before_keys, before_progress, timeout=6.0):
        state["round"] += 1
        return state["round"] <= 2      # 只有前两轮推进得动

    _patch_common(monkeypatch)
    monkeypatch.setattr(ff, "_wait_keys_change", fake_change)

    assert ff.burn_keys(10) == 2


def test_burn_stops_when_button_disappears(monkeypatch):
    """按钮消失（钥匙耗尽/界面被弹窗顶掉）时结束，不拿 None 坐标去点。"""
    monkeypatch.setattr(ff, "check_stop", lambda: None)
    monkeypatch.setattr(ff, "invalidate_screenshot_cache", lambda: None)
    monkeypatch.setattr(ff.time, "sleep", lambda _s: None)
    monkeypatch.setattr(ff, "_region_crop", lambda region: b"crop")
    monkeypatch.setattr(ff, "_wait_keys_change", lambda before_keys, before_progress, timeout=6.0: True)
    monkeypatch.setattr(ff, "game_client_region", lambda *a, **k: (0, 0, 1600, 900))
    positions = iter([(1000, 750), None])
    clicks = []

    def fake_find(template_path, *args, **kwargs):
        if template_path == ff.tpl_trigger_event:
            return None
        return next(positions)

    monkeypatch.setattr(ff, "find_center_silent", fake_find)
    monkeypatch.setattr(ff, "click_position", lambda pos, **kwargs: clicks.append(pos))

    assert ff.burn_keys(10) == 1
    assert clicks == [(1000, 750)]


def test_burn_uses_single_click_not_double(monkeypatch):
    """连点两下会白烧一整轮钥匙，必须 twice=False。"""
    seen = {}
    _patch_common(monkeypatch)
    monkeypatch.setattr(ff, "_wait_keys_change", lambda before_keys, before_progress, timeout=6.0: False)

    def fake_click(pos, wait=1.5, twice=True):
        seen["twice"] = twice

    monkeypatch.setattr(ff, "click_position", fake_click)
    ff.burn_keys(1)
    assert seen.get("twice") is False


def test_trigger_event_page_picks_first_faction(monkeypatch):
    """「触发事件」选择页出现时点第一个阵营，页消失即算处理完成。

    2026-11-18 实机：该页没有任何返回箭头/空白关闭提示，不处理就会把游戏留在
    死界面上，并让后续推图/愿望单/幻灵/循环推图四项连锁失败。
    """
    clicks = []
    state = {"shown": True}

    def fake_find(template_path, *args, **kwargs):
        return (760, 120) if (template_path == ff.tpl_trigger_event and state["shown"]) else None

    def fake_click(pos, **kwargs):
        clicks.append(pos)
        state["shown"] = False

    monkeypatch.setattr(ff, "find_center_silent", fake_find)
    monkeypatch.setattr(ff, "click_position", fake_click)
    monkeypatch.setattr(ff, "game_client_region", lambda *a, **k: (100, 50, 1600, 900))
    monkeypatch.setattr(ff, "log", lambda *a, **k: None)

    assert ff._handle_trigger_event() is True
    assert clicks == [(100 + ff.TRIGGER_OPTION_POS[0][0], 50 + ff.TRIGGER_OPTION_POS[0][1])]


def test_trigger_event_absent_does_not_click(monkeypatch):
    """没有选择页时不能盲点界面。"""
    clicks = []
    monkeypatch.setattr(ff, "find_center_silent", lambda *a, **k: None)
    monkeypatch.setattr(ff, "click_position", lambda *a, **k: clicks.append(a))
    monkeypatch.setattr(ff, "log", lambda *a, **k: None)

    assert ff._handle_trigger_event() is False
    assert clicks == []


def test_threshold_sits_below_the_measured_transition_noise():
    """阈值必须低于实测到的最差噪声底，否则页面切换动画会被误判成「钥匙已烧」。

    实测：稳定帧自匹配 1.000，但刚进页面的过渡期同一区域出现过 0.964–0.975。
    """
    observed_noise_floor = 0.964
    assert ff.KEYS_CHANGED_BELOW < observed_noise_floor, (
        f"阈值 {ff.KEYS_CHANGED_BELOW} 落在实测噪声带内，空烧会被当成推进成功"
    )


def test_main_caps_rounds_before_burning(monkeypatch):
    """轮数上限要夹住，防止配置里写进一个离谱值把钥匙一次烧光。"""
    asked = []
    monkeypatch.setattr(ff, "recover_to_main_interface", lambda: True)
    monkeypatch.setattr(ff, "_enter_fanfanle", lambda: True)
    monkeypatch.setattr(ff, "log", lambda *args, **kwargs: None)

    def fake_burn(max_rounds):
        asked.append(max_rounds)
        return 0

    monkeypatch.setattr(ff, "burn_keys", fake_burn)
    assert ff.main(max_rounds=9999) is True
    assert asked == [ff.MAX_ROUNDS_LIMIT]
