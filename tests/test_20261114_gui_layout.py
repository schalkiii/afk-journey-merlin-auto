"""GUI 布局与定时提醒的回归测试。

覆盖用户 2026-11-14 提的三件事：
- 「立即开始」按钮改名为「启动游戏并运行」；
- 定时注册后必须用显著方式提醒（常驻醒目横幅 + 标题角标 + 设定瞬间脉冲）；
- 窗口拖大拖小时控件不能被裁掉：控制栏按宽度自动折行、配置区可纵向滚动、
  主体与日志用可拖动分栏共享高度。

不建游戏、不启动真实定时循环（`_schedule_loop` 打桩），也不联网。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")

import bot_runtime
import Goldenhandmaidens as gui


@pytest.fixture
def root(tk_root):
    """共用 conftest 的会话级 Tk 根（已 withdraw，故用 winfo_manager 判可见性）。"""
    return tk_root


@pytest.fixture
def app(root, monkeypatch, tmp_path):
    monkeypatch.setattr(bot_runtime, "CONFIG_FILE", str(tmp_path / "game_bot_config.json"))
    # 构造期不注册全局热键、不联网检查更新
    monkeypatch.setattr(gui.GameBotGUI, "_register_hotkeys", lambda _self: None)
    monkeypatch.setattr(gui.GameBotGUI, "_auto_check_update", lambda _self: None)
    instance = gui.GameBotGUI(root)
    monkeypatch.setattr(instance, "log", lambda _msg: None)
    # 真实循环线程会在无 mainloop 的测试里抛「main thread is not in main loop」；
    # 脉冲会把 after 回调排到未来，跨用例触发到已销毁的控件上，这里默认关掉
    monkeypatch.setattr(instance, "_schedule_loop", lambda gen=None: None)
    monkeypatch.setattr(instance, "_pulse_banner", lambda step: None)
    yield instance
    instance._unregister_hotkeys()
    for child in list(root.winfo_children()):
        child.destroy()


def _rows(flow):
    return len({w.grid_info().get("row", 0) for w in flow.items})


def test_immediate_button_is_renamed(app):
    assert app.immediate_btn.cget("text") == "启动游戏并运行"


def test_master_button_swaps_text_and_style_with_run_state(app):
    app.is_running = False
    app.update_master_button()
    assert app.master_switch_btn.cget("text") == "开始运行 (F8)"
    assert app.master_switch_btn.cget("style") == "Accent.TButton"

    app.is_running = True
    app.update_master_button()
    assert app.master_switch_btn.cget("text") == "停止运行 (F9)"
    assert app.master_switch_btn.cget("style") == "Danger.TButton"


def test_schedule_banner_is_prominent_and_toggles(app, monkeypatch):
    pulses = []
    monkeypatch.setattr(app, "_pulse_banner", lambda step: pulses.append(step))
    app.cancel_schedule()
    assert app.schedule_banner.winfo_manager() == "", "未设定定时时横幅必须整条隐藏"

    app.schedule_hour_var.set(7)
    app.schedule_min_var.set(30)
    app.set_schedule()

    assert app.schedule_banner.winfo_manager() == "grid", "设定定时后必须出现醒目横幅"
    banner_text = app.schedule_banner_var.get()
    assert "07:30" in banner_text, "横幅要写清几点触发"
    assert "剩余" in banner_text, "横幅要带倒计时，用户才知道离触发还有多久"
    assert pulses == [0], "设定成功要闪一下横幅，作为「确实注册上了」的确认反馈"

    # 标题栏也要带角标：窗口被游戏盖住时只剩任务栏可见
    assert "定时 07:30" in _title(app)

    app.cancel_schedule()
    assert app.schedule_banner.winfo_manager() == "", "取消定时后横幅要收起"
    assert "定时" not in _title(app)


def _title(app):
    return app.root.title()


def test_schedule_countdown_updates_banner_not_the_toolbar(app):
    """倒计时只进横幅：塞进行内标签会每秒变长，把控制栏反复挤到折行。"""
    app.schedule_hour_var.set(6)
    app.schedule_min_var.set(5)
    app.set_schedule()
    app.update_schedule_status()

    assert app.schedule_status_label.cget("text") == "已定时 06:05"
    assert "06:05" in app.schedule_banner_var.get()
    assert "剩余" in app.schedule_banner_var.get()


def test_fire_while_running_rearms_the_daily_schedule(app, monkeypatch):
    """撞上正在运行的脚本时要跳过本轮，但必须把明天的排回去。

    旧实现在这里直接 return，等于「每天循环」在第一次撞车后静默失效到下次重启。
    """
    calls = []
    monkeypatch.setattr(app, "set_schedule", lambda: calls.append("rearm"))
    app.is_running = True
    app._last_fire_ts = 0.0
    app._fire_schedule()
    assert calls == ["rearm"]


def test_control_bar_wraps_instead_of_clipping(app):
    """窗口变窄时整组控件下移，而不是把「设定定时」挤出可视区。

    pack(side=LEFT) 不折行——这正是用户反馈「面板小了就看不到设定定时」的根因。
    """
    app.root.update_idletasks()   # 折行按 winfo_reqwidth 计算，先让布局算一轮
    wide = _rows(app._option_flow)
    app._option_flow.reflow(360)
    app._schedule_flow.reflow(360)
    assert _rows(app._option_flow) > wide, "窄宽度下选项必须换行"
    assert _rows(app._schedule_flow) > 1, "窄宽度下定时块必须换行"

    for flow in (app._option_flow, app._schedule_flow):
        for widget in flow.items:
            assert widget.winfo_manager() == "grid", "折行后每个控件都必须仍然被布局"
    assert app.sched_set_btn.winfo_manager() == "grid"


def test_minimum_width_keeps_every_toolbar_control(app, root):
    """缩到最小尺寸后，控制栏三层的每个控件都还在（没有 0 宽、没有未布局）。"""
    root.geometry("880x560")
    root.update_idletasks()

    controls = (
        app.master_switch_btn, app.immediate_btn, app.current_task_label,
        app.clear_log_btn, app.help_btn, app.sponsor_btn, app.update_btn,
        app.version_label, app.game_wait_spin, app.sched_hour_spin,
        app.sched_min_spin, app.sched_set_btn, app.schedule_status_label,
    )
    for widget in controls:
        assert widget.winfo_manager() in ("grid", "pack"), f"{widget} 没有被布局"
        assert int(widget.winfo_reqwidth()) > 0


def test_config_panel_scrolls_so_params_are_reachable(app):
    """配置区必须可纵向滚动：红点领取 9 个子项在小窗口下会被裁掉。"""
    canvas = app.script_panel_body.master
    assert isinstance(canvas, tk.Canvas)
    assert canvas in app._scroll_canvases
    assert canvas.cget("yscrollcommand"), "滚动条必须与 canvas 绑定"


def test_mousewheel_targets_nearest_scroll_area(app):
    """滚轮就近派发：嵌套滚动区（仓库英雄列表）不能被外层抢走。"""
    inner = app.script_panel_body
    assert app._nearest_scroll_canvas(inner) is inner.master

    box = app._checkbutton(app.param_frame, text="探针", variable=tk.BooleanVar())
    assert app._nearest_scroll_canvas(box) is inner.master
    assert app._nearest_scroll_canvas(app.master_switch_btn) is None
