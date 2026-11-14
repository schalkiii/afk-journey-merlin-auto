"""红点领取子项开关（GUI 侧）的回归测试。

真实构造 GUI，验证 9 个 claim_* 复选框默认全开，且点击后立即写回
script.params 并持久化到配置文件；不执行任何领取逻辑。
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")

import bot_runtime
import Goldenhandmaidens as gui

CLAIM_KEYS = (
    "claim_daily",
    "claim_guild",
    "claim_growth",
    "claim_season",
    "claim_homestead",
    "claim_season_book",
    "claim_laurel",
    "claim_idle",
    "claim_guild_war",
)


@pytest.fixture
def root(tk_root):
    """共用 conftest 的会话级 Tk 根，避免同进程反复建根导致随机 TclError。"""
    return tk_root


@pytest.fixture
def app(root, monkeypatch, tmp_path):
    monkeypatch.setattr(bot_runtime, "CONFIG_FILE", str(tmp_path / "game_bot_config.json"))
    instance = gui.GameBotGUI(root)
    monkeypatch.setattr(instance, "log", lambda _msg: None)
    yield instance
    instance._unregister_hotkeys()
    for child in list(root.winfo_children()):
        child.destroy()


def _select_hongbao(app):
    index = next(i for i, script in enumerate(app.scripts) if script.name == "红点领取")
    app.current_script_index = index
    app.update_script_panel()
    return index


def _claim_boxes(app):
    """9 个子项开关：勾选控件自绘（见 _ToggleBox），按标签文字取回。"""
    return {
        widget.label_text: widget for widget in app.param_frame.winfo_children()
        if getattr(widget, "label_text", None)
    }


def test_hongbao_panel_has_nine_checkboxes_default_true(app):
    _select_hongbao(app)

    assert set(app.hongbao_claim_vars) == set(CLAIM_KEYS)
    assert all(var.get() is True for var in app.hongbao_claim_vars.values())

    boxes = _claim_boxes(app)
    assert set(boxes) == {
        "每日任务", "公会任务", "成长挑战", "赛季任务", "家园目标",
        "赛季手册", "月桂之旅", "赛季挂机关卡", "公会征伐",
    }, "9 个子项必须都在面板上，否则用户没法单独关闭某一项"
    assert all(box.variable.get() is True for box in boxes.values())


def test_toggling_claim_guild_writes_back_and_persists(app):
    index = _select_hongbao(app)
    script = app.scripts[index]

    _claim_boxes(app)["公会任务"].toggle()  # 模拟用户取消勾选，走真实 command 链路

    assert app.hongbao_claim_vars["claim_guild"].get() is False
    assert script.params["claim_guild"] is False

    with open(bot_runtime.CONFIG_FILE, encoding="utf-8") as stream:
        saved = json.load(stream)
    assert saved["scripts"]["红点领取"]["params"]["claim_guild"] is False
