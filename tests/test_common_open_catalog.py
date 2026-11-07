"""玩法目录入口自证：首次点击被窗口激活吞掉时补点一次（不接触真实游戏）。

实测依据（2026-11-07）：同一坐标第一次点击无效、第二次才打开目录；旧流程点完即返回
True，后续卡片模板连续 8~15 秒全部落空，整条任务白等到超时。
"""
import common


def test_open_wanfamulu_retries_when_catalog_not_open(monkeypatch):
    """第一点击后目录标题未出现 → 补点一次；标题出现即返回 True。"""
    clicks = []
    titles = [None, (400, 30)]

    def fake_wait(template_path, name, *args, **kwargs):
        clicks.append(name)
        return True

    def fake_find(template_path, threshold=0.8, timeout=0, **kwargs):
        return titles.pop(0) if titles else (400, 30)

    monkeypatch.setattr(common, "wait_and_click", fake_wait)
    monkeypatch.setattr(common, "find_center_silent", fake_find)
    monkeypatch.setattr(common, "log", lambda *args, **kwargs: None)

    assert common.open_wanfamulu() is True
    assert clicks == ["wanfamulu", "wanfamulu"]


def test_open_wanfamulu_returns_false_when_entry_missing(monkeypatch):
    """主界面找不到玩法目录入口时不点击、直接失败。"""
    monkeypatch.setattr(common, "wait_and_click", lambda *args, **kwargs: False)
    monkeypatch.setattr(common, "find_center_silent", lambda *args, **kwargs: None)
    monkeypatch.setattr(common, "log", lambda *args, **kwargs: None)

    assert common.open_wanfamulu() is False
