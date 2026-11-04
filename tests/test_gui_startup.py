"""全局热键延后注册的回归测试。

`keyboard` 的导入与 add_hotkey 是启动时阻塞界面可操作的主要来源，所以注册被
挪到首帧之后的 after 回调。这里真实构造一次 GUI（不执行任何游戏操作），验证：
- 构造期间不注册热键（否则启动仍会被 keyboard 阻塞）；
- 首帧 + 延迟后才真正触发一次注册；
- 注册前调用 _unregister_hotkeys 不会因缺属性抛错。

无图形环境（纯命令行 CI）时整体跳过；测试不写真实配置文件，也不会装全局热键
（用记录器替换真实注册方法）。
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")

import bot_runtime
import Goldenhandmaidens as gui


@pytest.fixture
def root(tk_root):
    """共用 conftest 里的会话级 Tk 根：同进程再建第二个根会随机 TclError 导致整组 skip。"""
    return tk_root


def test_hotkey_registration_is_deferred_until_after_first_frame(root, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(bot_runtime, "CONFIG_FILE", str(tmp_path / "game_bot_config.json"))
    # 必须在构造前替换类方法，否则构造末尾的 after 会调度真实注册
    monkeypatch.setattr(gui.GameBotGUI, "_register_hotkeys", lambda _self: calls.append("registered"))

    instance = gui.GameBotGUI(root)
    monkeypatch.setattr(instance, "log", lambda _msg: None)
    monkeypatch.setattr(instance, "update_script_panel", lambda: None)
    try:
        assert calls == [], "构造期间不得注册热键，否则启动仍被 keyboard 阻塞"
        # 初始化过的占位字段：注册前调用 _unregister_hotkeys 不能 AttributeError
        assert instance._hotkey_lib is None
        assert instance._hk_start is None
        assert instance._hk_stop is None

        time.sleep(0.25)
        root.update_idletasks()
        root.update()
        assert calls == ["registered"], "首帧延迟后应恰好注册一次热键"
    finally:
        instance._unregister_hotkeys()
        # 销毁本实例的控件，避免下一个测试叠在上一个的界面上
        for child in list(root.winfo_children()):
            child.destroy()
