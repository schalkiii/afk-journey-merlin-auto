"""2026-11-24 复查：仓库快照缺英雄时的口径（用户约定：缺失＝巅峰+）。

用户反馈「仓库管理里埃德加和塞涅都配的是巅峰+，怎么还提示练度不足」。
根因是面板对**文件里没有的英雄**默认显示「巅峰+」，但磁盘上没有记录，
推图读取快照时按「未拥有」拒绝。2026-11-24 用户明确约定：
**缺记录一律按「巅峰+」处理**（面板显示、写盘、推图读取三处口径统一），
并在日常「仓库管理」里点名告警，方便发现过期快照。
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Goldenhandmaidens as gh
import push


def _fake_gui(logs):
    gui = object.__new__(gh.GameBotGUI)
    gui._hero_levels = {}
    gui.log = lambda msg, *a, **k: logs.append(msg)
    return gui


def test_write_defaults_missing_heroes_to_high(monkeypatch, tmp_path):
    """写盘时快照里没有的英雄落成「巅峰+」，与面板显示一致。"""
    target = tmp_path / "warehouse_heroes.txt"
    monkeypatch.setattr(gh, "WAREHOUSE_TXT_PATH", str(target))

    gh.GameBotGUI._write_warehouse_txt(_fake_gui([]))

    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines, "必须写出全量英雄表"
    assert all(line.endswith(",高") for line in lines)
    assert any(line.startswith("aidejia,") for line in lines)


def test_run_warehouse_warns_when_snapshot_missing_heroes(monkeypatch, tmp_path):
    """快照缺英雄时要明确告警（并说明按巅峰+兜底），不再静默「数据已就绪」。"""
    target = tmp_path / "warehouse_heroes.txt"
    target.write_text(
        "\n".join(f"{name},高" for name in gh.ALL_HERO_NAMES if name != "aidejia"),
        encoding="utf-8",
    )
    monkeypatch.setattr(gh, "WAREHOUSE_TXT_PATH", str(target))
    logs = []

    assert gh.GameBotGUI._run_warehouse(_fake_gui(logs), None) is True
    text = "\n".join(logs)
    assert "仓库快照缺少 1 个英雄" in text
    assert "巅峰+" in text
    assert "埃德加" in text, "告警里应点名缺失英雄，方便直接去补配"


def test_no_warning_when_snapshot_covers_all_heroes(monkeypatch, tmp_path):
    """快照完整时不应刷告警。"""
    target = tmp_path / "warehouse_heroes.txt"
    target.write_text(
        "\n".join(f"{name},高" for name in gh.ALL_HERO_NAMES), encoding="utf-8"
    )
    monkeypatch.setattr(gh, "WAREHOUSE_TXT_PATH", str(target))
    logs = []

    assert gh.GameBotGUI._run_warehouse(_fake_gui(logs), None) is True
    assert not any("仓库快照缺少" in msg for msg in logs)


def test_panel_defaults_missing_heroes_to_high():
    """面板显示与推图口径一致：文件里没有的英雄显示「巅峰+」。"""
    source = inspect.getsource(gh.GameBotGUI.create_warehouse_params)
    assert 'hero_levels.get(hero_name, "高")' in source


def test_load_warehouse_levels_fills_missing_as_high(monkeypatch, tmp_path):
    """推图读取快照时，缺记录（含新英雄）必须补成「巅峰+」而不是未拥有。"""
    target = tmp_path / "warehouse_heroes.txt"
    target.write_text("ade,低\n", encoding="utf-8")
    monkeypatch.setattr(push, "WAREHOUSE_TXT_PATH", str(target))

    levels = push._load_warehouse_levels()

    assert levels["ade"] == "低", "已有记录必须保持原值"
    assert levels["aidejia"] == "高"
    assert levels["sainie"] == "高"
