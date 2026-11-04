"""最小冒烟 / 回归测试。

覆盖：
- 所有顶层模块可正常导入（打包与依赖健康度）。
- 阵容可采纳判定 `_is_lineup_acceptable` 的核心逻辑（通过 monkeypatch 固定练度字典，
  使断言不依赖真实 SPECIAL_HERO_SET / LEVEL_SCORE，避免脆断）。判定本体在
  `common.is_lineup_acceptable`，push / flow_tower 只是注入各自常量的薄包装，所以
  特殊角色分支与「需求档位认不出来」的兜底都经由 push 的包装覆盖。
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


def test_lineup_acceptable_special_hero(monkeypatch):
    """特殊角色（common.py:1076 分支）：拥有即可且忽略需求档位，但未拥有仍拒绝。"""
    push = importlib.import_module("push")
    monkeypatch.setattr(push, "LEVEL_SCORE", {"未拥有": 0, "低": 1, "中": 2, "高": 3})
    monkeypatch.setattr(push, "SPECIAL_HERO_SET", {"meimo"})

    # 练度「低」而需求「高」：普通角色会被拒，特殊角色忽略需求 -> 通过
    assert push._is_lineup_acceptable({"meimo": "低"}, [("meimo", "高")]) is True
    # 特殊角色「未拥有」：拥有即可的前提不成立 -> 拒绝
    assert push._is_lineup_acceptable({}, [("meimo", "低")]) is False


def test_lineup_acceptable_unrecognized_need_level(monkeypatch):
    """需求档位认不出来时（common.py:1084 兜底默认按「低」）：非未拥有即可通过，未拥有仍拒绝。"""
    push = importlib.import_module("push")
    monkeypatch.setattr(push, "LEVEL_SCORE", {"未拥有": 0, "低": 1, "中": 2, "高": 3})
    monkeypatch.setattr(push, "SPECIAL_HERO_SET", set())

    # 需求「极高」不在 LEVEL_SCORE 里 -> 按「低」(1) 处理，自家「低」(1) 不小于它 -> 通过
    assert push._is_lineup_acceptable({"gubian": "低"}, [("gubian", "极高")]) is True
    # 兜底仍是「低」这一档，未拥有 (0) 依旧不够 -> 拒绝
    assert push._is_lineup_acceptable({}, [("gubian", "极高")]) is False
