"""左侧列表的启用勾选框与状态颜色标注的回归测试。

真实构造 GUI（不执行任何游戏操作）验证：
- 状态色映射覆盖运行循环可能写入的全部 status 值，没有漏色的状态；
- 刷新后每行的状态色块文字/底色与 script.status 一致；
- 勾选框改动 enabled 并立即持久化（用户设置写盘，不再被程序自动改）；
- 拖拽重排时行 Frame、勾选框、状态色块、变量与数据全部同步换位；
- 启用状态能原样读回（不再有「完成即自动关闭」把设置改掉）。

无图形环境（纯命令行 CI）时整体跳过；测试不写真实配置文件。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")

import bot_runtime
import Goldenhandmaidens as gui

# run_scripts_thread / _begin_run / stop_all 可能写入的全部状态值
ALL_STATUSES = ("运行中", "等待中", "完成", "失败", "错误", "已停止")


@pytest.fixture
def root(tk_root):
    """共用 conftest 里的会话级 Tk 根：同进程再建第二个根会随机 TclError 导致整组 skip。"""
    return tk_root


@pytest.fixture
def app(root, monkeypatch, tmp_path):
    config_path = tmp_path / "game_bot_config.json"
    monkeypatch.setattr(bot_runtime, "CONFIG_FILE", str(config_path))
    instance = gui.GameBotGUI(root)
    monkeypatch.setattr(instance, "log", lambda _msg: None)
    yield instance
    instance._unregister_hotkeys()
    for child in list(root.winfo_children()):
        child.destroy()


def test_status_colors_cover_every_status_the_loop_writes():
    for status in ALL_STATUSES:
        assert status in gui.STATUS_COLORS, f"{status} 没有配色，会退回中性色看不出来"


def test_row_status_label_reflects_script_status(app):
    app.scripts[2].status = "失败"
    app.scripts[3].status = "完成"
    app.update_dashboard_buttons()

    assert app.script_status_labels[2].cget("text") == "失败"
    assert app.script_status_labels[2].cget("bg") == gui.STATUS_COLORS["失败"][0]
    assert app.script_status_labels[3].cget("bg") == gui.STATUS_COLORS["完成"][0]
    # 没跑过的行保持中性：不显示文字，避免满屏色块反而看不出重点
    assert app.script_status_labels[0].cget("text") == ""
    assert app.script_status_labels[0].cget("bg") == gui.STATUS_NEUTRAL[0]


def test_row_checkbox_updates_enabled_and_persists(app):
    target = app.scripts[5]
    before = target.enabled
    app.script_checks[5].invoke()      # 模拟用户点勾选框（走真实 command 链路）

    assert target.enabled == (not before), "勾选框应直接翻转该功能的启用状态"
    assert app.script_enabled_vars[5].get() == target.enabled

    saved = gui.load_config()
    assert saved["scripts"][target.name]["enabled"] == target.enabled, "勾选必须立即写盘"


def test_reorder_keeps_every_row_widget_in_sync(app):
    names_before = [s.name for s in app.scripts]
    app._move_script(len(app.scripts) - 1, 0)
    names_after = [s.name for s in app.scripts]

    moved = names_before[-1]
    assert names_after[0] == moved
    # 六份并行集合必须同序，否则勾选框会控制到别的任务上
    assert [btn.cget("text") for btn in app.script_buttons] == names_after
    assert len(app.script_rows) == len(app.script_checks) == len(app.script_status_labels) \
        == len(app.script_enabled_vars) == len(app.scripts)

    # 首位行的勾选状态应跟着被拖动的功能走，不是原来第一行的
    assert app.script_enabled_vars[0].get() == app.scripts[0].enabled


def test_enabled_state_survives_roundtrip_without_auto_disable(app):
    target = app.scripts[1]
    target.enabled = True
    app.update_dashboard_buttons()
    app.save_config()

    # 「完成即停用」的旧行为会让第二天的任务被静默跳过：字段应已整体移除
    assert not hasattr(bot_runtime.ScriptConfig("某功能"), "daily_reset")

    reloaded = gui.GameBotGUI(app.root)
    try:
        assert reloaded.scripts[1].enabled is True, "用户勾选必须原样读回"
    finally:
        reloaded._unregister_hotkeys()
        for child in list(reloaded.root.winfo_children()):
            if child is not app.root:
                child.destroy()
