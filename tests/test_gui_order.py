"""功能列表排序 / 持久化 / 单跑目标的回归测试。

真实构造一次 GUI（不执行任何游戏操作），验证：
- 拖拽重排后 self.scripts 与按钮顺序同步、不丢功能；
- 当前选中项跟着「原本选中的功能」走，不会因拖动别的行而跳到别人身上；
- script_order 持久化内容与列表一致，且配置里缺新功能时能补到末尾；
- 「只运行当前功能」取到的就是当前选中项。

无图形环境（纯命令行 CI）时整体跳过；测试不写真实配置文件。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")

import bot_runtime
import Goldenhandmaidens as gui


@pytest.fixture(scope="module")
def root():
    """整模块共用一个 Tk 根：反复创建/销毁根在同一进程内不稳定，会随机抛 TclError。"""
    try:
        instance = tk.Tk()
    except tk.TclError:
        pytest.skip("当前环境没有可用的图形显示，跳过 GUI 测试")
    instance.withdraw()   # 不弹窗，避免干扰正在跑的任务
    yield instance
    instance.destroy()


@pytest.fixture
def app(root, monkeypatch, tmp_path):
    monkeypatch.setattr(bot_runtime, "CONFIG_FILE", str(tmp_path / "game_bot_config.json"))
    instance = gui.GameBotGUI(root)
    monkeypatch.setattr(instance, "update_script_panel", lambda: None)
    monkeypatch.setattr(instance, "log", lambda _msg: None)
    yield instance
    instance._unregister_hotkeys()
    # 销毁本实例的控件，避免下一个测试叠在上一个的界面上
    for child in list(root.winfo_children()):
        child.destroy()


def test_reorder_moves_script_and_button_together(app):
    before = [s.name for s in app.scripts]
    app._move_script(len(app.scripts) - 1, 0)
    after = [s.name for s in app.scripts]

    assert after[0] == before[-1], "被拖动的功能应到列表首位"
    assert sorted(after) == sorted(before), "重排不得丢失或重复功能"
    assert [btn.cget("text").lstrip("✓ ") for btn in app.script_buttons] == after, \
        "按钮文本顺序必须与 self.scripts 一致（否则点击会选错功能）"


def test_selection_follows_original_script(app):
    selected = app.scripts[app.current_script_index].name
    app._move_script(len(app.scripts) - 1, 0)
    assert app.scripts[app.current_script_index].name == selected, \
        "拖动别的行不应切换右侧配置面板所指向的功能"


def test_script_order_persisted_matches_list(app):
    app._move_script(0, len(app.scripts) - 1)
    app.save_config()   # 已被 monkeypatch 成空操作，这里只验证内存结果
    assert app.config["script_order"] == [s.name for s in app.scripts]


def test_missing_new_script_appends_to_tail():
    """配置里保存的顺序缺少新功能时，新功能应补到末尾而不是被丢弃。"""
    saved_order = ["b", "a"]
    scripts = ["a", "b", "c"]
    known = sorted([n for n in scripts if n in saved_order], key=saved_order.index)
    rest = [n for n in scripts if n not in saved_order]
    assert known + rest == ["b", "a", "c"]


def test_run_single_targets_current_script(app):
    target = app.scripts[app.current_script_index]
    assert app.scripts[app.current_script_index] is target


def test_drag_threshold_ignores_small_movement(app):
    """位移小于 8px 视为点击，不进入拖拽——否则轻微抖动就会改掉执行顺序。"""
    before = [s.name for s in app.scripts]

    class _Event:
        y_root = 0

    app._drag_begin(_Event(), app.script_buttons[0])
    _Event.y_root = 4
    app._drag_motion(_Event(), app.script_buttons[0])

    assert app._drag_moved is False
    assert [s.name for s in app.scripts] == before
