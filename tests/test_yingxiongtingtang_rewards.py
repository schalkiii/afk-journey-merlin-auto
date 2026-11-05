"""英雄厅堂挂机奖励领取（中央宝箱 + 右上角）的单元测试。

测试环境没有游戏窗口：模板匹配、点击、等待与关弹窗全部在模块级接缝打桩，
只验证「在哪个区域探哪些模板、命中后点几次」的决策逻辑。
"""
import yingxiongtingtang as yx

# 每个区域只给一个命中模板：中央是宝箱，右上是单个「领取」。
REGION_HITS = {
    yx.HERO_CENTER_CHEST_REGION: (yx.tpl_baoxiang_full, (800, 450)),
    yx.HERO_TOP_RIGHT_REGION: (yx.tpl_lingqu, (1450, 150)),
}


def _stub_claim_seams(monkeypatch, hits):
    """桩掉领取接缝；hits 是 {client_region: (template_path, pos)}，返回调用记账。"""
    clicks, waits, closes, finds = [], [], [], []

    def fake_find(template_path, threshold=0.8, region=None, timeout=0,
                  interval=0.5, client_region=None):
        finds.append((template_path, client_region))
        hit = hits.get(client_region)
        if hit and hit[0] == template_path:
            return hit[1]
        return None

    def fake_click(pos, wait=1.5, twice=True):
        clicks.append((pos, wait, twice))
        return True

    def fake_wait_click(template_path, name, threshold=0.8, timeout=None, **kwargs):
        waits.append((template_path, name, timeout))
        return True

    monkeypatch.setattr(yx, "find_center_silent", fake_find)
    monkeypatch.setattr(yx, "click_position", fake_click)
    monkeypatch.setattr(yx, "wait_and_click", fake_wait_click)
    monkeypatch.setattr(yx, "dismiss_popup_away_from", lambda: closes.append("close"))
    monkeypatch.setattr(yx, "log", lambda *args, **kwargs: None)
    return clicks, waits, closes, finds


def test_claim_scans_center_chest_and_top_right_reward(monkeypatch):
    """中央命中宝箱、右上命中「领取」：每个区域各点一次，并等收获奖励、关弹窗。"""
    clicks, waits, closes, finds = _stub_claim_seams(monkeypatch, REGION_HITS)

    assert yx._claim_chest_and_reward(yx.HERO_CENTER_CHEST_REGION, "中央宝箱") is True
    assert yx._claim_chest_and_reward(yx.HERO_TOP_RIGHT_REGION, "右上角奖励") is True

    # 中央首个模板即命中；右上要先跳过宝箱才命中「领取」，探测顺序不能颠倒
    assert finds == [
        (yx.tpl_baoxiang_full, yx.HERO_CENTER_CHEST_REGION),
        (yx.tpl_baoxiang_full, yx.HERO_TOP_RIGHT_REGION),
        (yx.tpl_lingqu, yx.HERO_TOP_RIGHT_REGION),
    ]
    assert clicks == [
        ((800, 450), 1.5, False),
        ((1450, 150), 1.5, False),
    ]
    assert [template for template, _name, _timeout in waits] == [
        yx.tpl_shouhuojiangli,
        yx.tpl_shouhuojiangli,
    ]
    assert closes == ["close", "close"]


def test_claim_returns_false_without_click_when_region_has_no_reward(monkeypatch):
    """区域内三种模板都没命中：返回 False，且不得点击、不得关弹窗。"""
    clicks, waits, closes, finds = _stub_claim_seams(monkeypatch, {})

    assert yx._claim_chest_and_reward(yx.HERO_CENTER_CHEST_REGION, "中央宝箱") is False

    assert clicks == []
    assert waits == []
    assert closes == []
    assert [template for template, _region in finds] == [
        yx.tpl_baoxiang_full,
        yx.tpl_lingqu,
        yx.tpl_yijianlingqu,
    ]


def test_main_claims_before_upgrade_and_keeps_return_true(monkeypatch):
    """领奖失败不阻断升级：先扫中央、再扫右上，然后照常快速升级并返回 True。"""
    order = []

    monkeypatch.setattr(yx, "_enter_hero_hall", lambda: True)
    monkeypatch.setattr(
        yx, "_claim_chest_and_reward",
        lambda region, label: order.append(label) or False,
    )
    monkeypatch.setattr(yx, "quick_upgrade", lambda times: order.append(f"upgrade{times}") or 2)
    monkeypatch.setattr(yx, "recover_to_main_interface", lambda *args, **kwargs: True)
    monkeypatch.setattr(yx, "log", lambda *args, **kwargs: None)

    assert yx.main(3) is True
    assert order == ["中央宝箱", "右上角奖励", "upgrade3"]
