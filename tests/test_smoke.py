"""最小冒烟 / 回归测试。

覆盖：
- 所有顶层模块可正常导入（打包与依赖健康度）。
- 阵容可采纳判定 `_is_lineup_acceptable` 的核心逻辑（通过 monkeypatch 固定练度字典，
  使断言不依赖真实 SPECIAL_HERO_SET / LEVEL_SCORE，避免脆断）。
"""
import glob
import importlib
import os


def test_all_modules_import():
    mods = [
        os.path.splitext(f)[0]
        for f in glob.glob("*.py")
        if not f.startswith("_") and f != "start.py"
    ]
    for m in mods:
        importlib.import_module(m)


def test_lineup_acceptable(monkeypatch):
    push = importlib.import_module("push")
    # 固定练度排序与特殊角色集合，使判定路径确定可控
    monkeypatch.setattr(push, "LEVEL_SCORE", {"未拥有": 0, "低": 1, "中": 2, "高": 3})
    monkeypatch.setattr(push, "SPECIAL_HERO_SET", set())

    # 自家练度 >= 需求 -> 通过
    assert push._is_lineup_acceptable({"gubian": "高"}, [("gubian", "低")]) is True
    # 自家练度 < 需求 -> 拒绝
    assert push._is_lineup_acceptable({"gubian": "低"}, [("gubian", "高")]) is False
    # 未拥有 -> 拒绝
    assert push._is_lineup_acceptable({}, [("gubian", "低")]) is False
