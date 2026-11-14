"""子进程启动的统一封装：控制台子程序一律不弹黑框。

为什么需要这一层：打包成 `console=False`（PE 子系统 = WINDOWS，见
goldenhandmaidens.spec）之后，本进程**没有控制台**。此时 CreateProcess 启动任何
「控制台子系统」的子程序，Windows 都会给它新建一个控制台窗口——用户看到的就是一闪
而过的黑色 cmd 框。实测触发点：

- 启动游戏：读桌面 .lnk 的目标，走 `powershell`（`bot_runtime.read_game_shortcut`）；
- 运行前后探测 / 回收点击注入器：`tasklist` / `taskkill`（`common`、GUI）；
- 安装更新：`cmd` 执行 update.bat（`updater`）。

注意这不是「打包参数写错了」：`console=False` 已经生效（成品 PE Subsystem=2），
黑框来自上述**每一个**子进程，改 spec 改不掉，只能在创建子进程时带上隐藏标志。

CREATE_NO_WINDOW 让子进程完全不带控制台；STARTF_USESHOWWINDOW + SW_HIDE 是双保险
（少数子程序会自己调 ShowWindow 把窗口显示出来）。两个标志只在 Windows 有意义，
其他平台返回空参数、行为与裸调 subprocess 一致。
"""

import os
import subprocess

# 0x08000000 是 CREATE_NO_WINDOW 的字面值：老版本 Python 没导出该常量时兜底用
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def hidden_kwargs():
    """返回隐藏控制台窗口所需的 run/Popen 关键字；非 Windows 返回空字典。

    单独暴露出来是为了让调用方能在需要时**自己合并**（例如要就地覆盖
    creationflags），同时用例可以直接断言这两个标志确实被设上。
    """
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    # dwFlags 必须先置 STARTF_USESHOWWINDOW，否则 wShowWindow 会被系统忽略
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": startupinfo, "creationflags": _CREATE_NO_WINDOW}


def run_hidden(args, **kwargs):
    """同 `subprocess.run`，但子进程不带控制台窗口。

    调用方显式传入的 startupinfo / creationflags / check 优先（用 setdefault 合并），
    便于用例注入替身或做特殊处理。
    """
    # check 单独取出来显式传：留在 **kwargs 里静态检查看不到，会被判「没写 check」
    check = kwargs.pop("check", False)
    for key, value in hidden_kwargs().items():
        kwargs.setdefault(key, value)
    return subprocess.run(args, check=check, **kwargs)


def popen_hidden(args, **kwargs):
    """同 `subprocess.Popen`，但子进程不带控制台窗口。"""
    for key, value in hidden_kwargs().items():
        kwargs.setdefault(key, value)
    return subprocess.Popen(args, **kwargs)
