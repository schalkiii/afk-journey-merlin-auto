"""2026-11-24 复查：仓库快照里没有的英雄必须按「未拥有」显示与写盘。

用户反馈「仓库管理里埃德加和塞涅都配的是巅峰+，怎么还提示练度不足」。
实际原因是面板对**文件里没有的英雄**默认显示「巅峰+」（`hero_levels.get(name, "高")`），
看着配好了，磁盘上根本没有这条记录；推图读取快照时按「未拥有」处理，于是每一套带
这两名英雄的推荐阵容都被拒绝。写盘默认值同样是「高」，方向也是错的。
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Goldenhandmaidens as gh


def _fake_gui(logs):
    gui = object.__new__(gh.GameBotGUI)
    gui._hero_levels = {}
    gui.log = lambda msg, *a, **k: logs.append(msg)
    return gui


def test_write_defaults_missing_heroes_to_not_owned(monkeypatch, tmp_path):
    """写盘时快照里没有的英雄必须落成「未拥有」，不能默认成巅峰+。"""
    target = tmp_path / "warehouse_heroes.txt"
    monkeypatch.setattr(gh, "WAREHOUSE_TXT_PATH", str(target))

    gh.GameBotGUI._write_warehouse_txt(_fake_gui([]))

    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines, "必须写出全量英雄表"
    assert all(line.endswith(",未拥有") for line in lines)
    assert any(line.startswith("aidejia,") for line in lines)


def test_run_warehouse_warns_when_snapshot_missing_heroes(monkeypatch, tmp_path):
    """快照缺英雄时要明确告警（并说明按未拥有处理），不再静默「数据已就绪」。"""
    target = tmp_path / "warehouse_heroes.txt"
    # 除埃德加外全都有：验证告警会点名真正缺失的英雄
    target.write_text(
        "\n".join(f"{name},高" for name in gh.ALL_HERO_NAMES if name != "aidejia"),
        encoding="utf-8",
    )
    monkeypatch.setattr(gh, "WAREHOUSE_TXT_PATH", str(target))
    logs = []

    assert gh.GameBotGUI._run_warehouse(_fake_gui(logs), None) is True
    text = "\n".join(logs)
    assert "仓库快照缺少 1 个英雄" in text
    assert "未拥有" in text
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


def test_panel_defaults_missing_heroes_to_not_owned():
    """面板显示必须与推图判定一致：文件里没有的英雄显示「未拥有」。"""
    source = inspect.getsource(gh.GameBotGUI.create_warehouse_params)
    assert 'hero_levels.get(hero_name, "未拥有")' in source
