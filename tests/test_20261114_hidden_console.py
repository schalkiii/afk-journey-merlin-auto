"""子进程「不弹黑色 cmd 框」的回归测试。

背景：打包成品是 GUI 子系统（`console=False`，实测 PE Subsystem=2），进程本身没有
控制台。此时创建任何控制台子程序（tasklist / taskkill / powershell / cmd）都会给
它新建一个控制台窗口——用户看到的就是每次启动/关闭工具时一闪的黑框。

所以规则只有一条：**业务代码不许裸调 subprocess**，一律走 `proc_util` 的
`run_hidden` / `popen_hidden`。这里用两种方式守住：
- 行为：断言封装真的带上了 CREATE_NO_WINDOW + STARTF_USESHOWWINDOW/SW_HIDE；
- 结构：AST 扫描全仓，任何文件（`proc_util.py` 除外）出现 subprocess.run/Popen
  调用即失败——新增调用点会自动被拦下。
"""
import ast
import os
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot_runtime
import common
import Goldenhandmaidens as gui
import proc_util

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 唯一允许直接创建子进程的模块：其余代码必须经由它，才能保证隐藏标志一定被带上
WRAPPER_MODULE = "proc_util.py"


def _capture_run(monkeypatch, stdout=b""):
    """把 subprocess.run 换成记录器，返回被调用时的 kwargs 列表。"""
    calls = []

    def fake(args, **kwargs):
        calls.append({"args": args, **kwargs})
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(proc_util.subprocess, "run", fake)
    return calls


def test_hidden_kwargs_carry_no_window_flags():
    kwargs = proc_util.hidden_kwargs()
    if os.name != "nt":
        assert kwargs == {}
        return
    assert kwargs["creationflags"] == proc_util.subprocess.CREATE_NO_WINDOW
    startupinfo = kwargs["startupinfo"]
    assert startupinfo.dwFlags & proc_util.subprocess.STARTF_USESHOWWINDOW
    assert startupinfo.wShowWindow == proc_util.subprocess.SW_HIDE


def test_run_hidden_merges_flags_and_lets_caller_override(monkeypatch):
    calls = _capture_run(monkeypatch)
    proc_util.run_hidden(["tasklist"], capture_output=True)
    proc_util.run_hidden(["tasklist"], creationflags=0x08000000)

    assert len(calls) == 2
    assert calls[0]["creationflags"] == proc_util.subprocess.CREATE_NO_WINDOW
    assert calls[1]["creationflags"] == 0x08000000, "调用方显式指定的标志优先"
    assert "startupinfo" in calls[0]


def test_probe_paths_run_without_console(monkeypatch):
    """真实调用路径：注入器探测（tasklist）必须带隐藏标志。"""
    calls = _capture_run(monkeypatch, stdout=b"")
    common.clicker_process_alive()
    assert calls, "探测注入器至少要跑一次 tasklist"
    assert all(call["creationflags"] == proc_util.subprocess.CREATE_NO_WINDOW
               for call in calls)


def test_taskkill_and_tasklist_in_gui_hide_window(monkeypatch):
    calls = _capture_run(monkeypatch, stdout=b"AutoHotkey")
    gui.GameBotGUI._taskkill(["/F", "/IM", "click_from_file.exe"])
    gui.GameBotGUI._pid_is_clicker(4321)

    assert [call["args"][0] for call in calls] == ["taskkill", "tasklist"]
    assert all(call["creationflags"] == proc_util.subprocess.CREATE_NO_WINDOW
               for call in calls)


def test_read_game_shortcut_powershell_hides_window(monkeypatch):
    """启动游戏前要读 .lnk 目标，走 powershell——这里必须同样隐藏。"""
    calls = _capture_run(monkeypatch, stdout="TARGET=C:/game.exe\nARGS=\nWORKDIR=C:/\n")
    target, args, workdir = bot_runtime.read_game_shortcut("C:/fake.lnk")

    assert (target, args, workdir) == ("C:/game.exe", "", "C:/")
    assert calls[0]["args"][0] == "powershell"
    assert calls[0]["creationflags"] == proc_util.subprocess.CREATE_NO_WINDOW


def _bare_subprocess_calls(path):
    """找出该文件里直接调用 subprocess.run/Popen/call/check_output 的位置。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if (isinstance(owner, ast.Name) and owner.id == "subprocess"
                and node.func.attr in {"run", "Popen", "call", "check_output"}):
            found.append(f"{path.name}:{node.lineno} subprocess.{node.func.attr}")
    return found


def test_no_bare_subprocess_calls_outside_wrapper():
    offenders = []
    for path in sorted(ROOT.glob("*.py")):
        if path.name == WRAPPER_MODULE:
            continue
        offenders.extend(_bare_subprocess_calls(path))

    assert not offenders, (
        "以下位置直接创建了子进程，会重新带出黑色 cmd 框；请改走 "
        "proc_util.run_hidden / popen_hidden：\n" + "\n".join(offenders)
    )


def test_wrapper_itself_keeps_using_creation_flags():
    """负验证护栏：封装内部一旦去掉隐藏参数，前面的结构检查就形同虚设。"""
    source = (ROOT / WRAPPER_MODULE).read_text(encoding="utf-8")
    assert "CREATE_NO_WINDOW" in source
    assert "STARTF_USESHOWWINDOW" in source
    assert "SW_HIDE" in source
