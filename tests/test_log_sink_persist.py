"""子脚本日志必须真正落盘的回归测试。

排查「没领到 / 识别没命中」全靠 `game_bot.log` 里的子脚本行，但 sink 只挂 `_enqueue_log`
时这些行只进界面面板、不进文件（实测用户跑完一轮，日志里除了开始/结束两条外搜不到任何
【家园愿望单】行）。这里守住两条性质：
- `common.log(...)` 一行落盘且带时间戳；
- 一条消息只落盘一行（面板与文件各一次，不能重复写文件）。
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")

import bot_runtime
import common
import Goldenhandmaidens as gui

LINE_WITH_TIMESTAMP = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] .+$")


@pytest.fixture
def root(tk_root):
    """共用会话级 Tk 根：同进程再建第二个根会随机 TclError 导致整组 skip。"""
    return tk_root


@pytest.fixture
def app(root, monkeypatch, tmp_path):
    """真实构造 GUI（不做任何游戏操作），配置与汇聚 sink 都隔离到临时环境。"""
    monkeypatch.setattr(bot_runtime, "CONFIG_FILE", str(tmp_path / "game_bot_config.json"))
    # 构造函数会改写模块级的 _log_sink；先登记原值，用例结束由 monkeypatch 还原，
    # 否则残留的 sink 指向已销毁的实例，会污染后续用例。
    monkeypatch.setattr(common, "_log_sink", None)
    instance = gui.GameBotGUI(root)
    yield instance
    instance._unregister_hotkeys()
    for child in list(root.winfo_children()):
        child.destroy()


def test_gui_wires_the_shared_sink_to_the_file_writing_log(app):
    assert common._log_sink == app.log, (
        "子脚本日志的汇聚出口必须接到会落盘的 log()，"
        "只接 _enqueue_log 会让盘上的日志缺掉全部子脚本细节行"
    )


def test_subscript_log_line_is_persisted_with_timestamp(app, monkeypatch, tmp_path):
    log_path = tmp_path / "game_bot.log"
    monkeypatch.setattr(bot_runtime, "LOG_FILE", str(log_path))

    common.log("【家园愿望单】当前不在家园视图，点击返回箭头后重试")

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, f"一条子脚本日志应只落盘一行，实际 {lines}"
    assert LINE_WITH_TIMESTAMP.match(lines[0]), f"缺时间戳：{lines[0]!r}"
    assert "当前不在家园视图" in lines[0]
