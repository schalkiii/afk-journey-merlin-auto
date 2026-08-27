"""
launch_game.py — 通过桌面「剑与远征：启程」快捷方式启动游戏，并可一键联动启动本项目脚本。

原理：读取桌面 .lnk 快捷方式中的「目标路径」和「参数」，用同样的命令直接启动游戏，
      相当于用代码代替双击快捷方式（从而跳过手动点启动器的步骤）。

用法：
    python launch_game.py                 # 仅启动游戏
    python launch_game.py --bot           # 启动游戏 + 启动本项目脚本(GUI)
    python launch_game.py --bot --delay 5 # 启动游戏，等待 5 秒后启动脚本

说明：
    - 若桌面快捷方式指向「游戏本体 exe」且带有 --env_id/--version/--env 等参数，
      则本脚本会直接把游戏跑起来（绕过启动器）。这正是前次调研中"命令行直启"的方案。
    - 若快捷方式只指向「启动器(launcher)」，则本脚本只会打开启动器，
      你需要在启动器里点一次开始。想彻底免点击，可把桌面快捷方式改为指向游戏本体 exe。
    - 带 --bot 时，脚本启动后会按 GUI 中「启动后自动运行」的勾选状态决定是否立即开始运行。
"""

import argparse
import os
import shlex
import subprocess
import sys
import time

# 桌面快捷方式候选名称（文件名包含其一即视为匹配）
SHORTCUT_KEYWORDS = ["剑与远征", "启程", "afk", "afkj"]


def find_shortcut():
    """在用户桌面与公共桌面查找剑与远征：启程的 .lnk 快捷方式。"""
    desktop_dirs = []
    user_profile = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if user_profile:
        desktop_dirs.append(os.path.join(user_profile, "Desktop"))
        desktop_dirs.append(os.path.join(user_profile, "OneDrive", "Desktop"))
    public = os.environ.get("PUBLIC")
    if public:
        desktop_dirs.append(os.path.join(public, "Desktop"))

    candidates = []
    seen = set()
    for d in desktop_dirs:
        if not d or d in seen or not os.path.isdir(d):
            continue
        seen.add(d)
        for name in os.listdir(d):
            if name.lower().endswith(".lnk"):
                low = name.lower()
                if any(k.lower() in low for k in SHORTCUT_KEYWORDS):
                    candidates.append(os.path.join(d, name))
    return candidates


def read_shortcut(lnk_path):
    """通过 PowerShell 的 WScript.Shell 读取 .lnk 的目标路径、参数、工作目录。"""
    ps = (
        "$WshShell = New-Object -ComObject WScript.Shell;"
        "$s = $WshShell.CreateShortcut('" + lnk_path.replace("'", "''") + "');"
        "Write-Output ('TARGET=' + $s.TargetPath);"
        "Write-Output ('ARGS=' + $s.Arguments);"
        "Write-Output ('WORKDIR=' + $s.WorkingDirectory);"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    target, args, workdir = "", "", ""
    for line in proc.stdout.splitlines():
        if line.startswith("TARGET="):
            target = line[len("TARGET="):].strip()
        elif line.startswith("ARGS="):
            args = line[len("ARGS="):].strip()
        elif line.startswith("WORKDIR="):
            workdir = line[len("WORKDIR="):].strip()
    return target, args, workdir


def launch_game():
    candidates = find_shortcut()
    if not candidates:
        print("未找到「剑与远征：启程」桌面快捷方式。请确认桌面存在该游戏快捷方式。")
        return None
    lnk = candidates[0]
    print(f"找到快捷方式: {lnk}")
    target, args, workdir = read_shortcut(lnk)
    if not target:
        print("无法读取快捷方式的目标路径。")
        return None
    print(f"目标  : {target}")
    print(f"参数  : {args}")
    print(f"工作目录: {workdir}")

    cmd = [target] + (shlex.split(args) if args else [])
    try:
        subprocess.Popen(cmd, cwd=workdir or None)
        print("已发送游戏启动命令。")
        return target
    except Exception as e:
        print(f"启动游戏失败: {e}")
        return None


def launch_bot():
    # 固定走 python 源码启动，确保 GUI 中的「启动后自动运行 / F8~F9 热键」等新功能生效
    # （release 版 goldenhandmaidens.exe 未包含这些功能，故此处不优先用 exe）
    here = os.path.dirname(os.path.abspath(__file__))
    bot_entry = os.path.join(here, "Goldenhandmaidens.py")
    if not os.path.exists(bot_entry):
        print(f"未找到脚本入口: {bot_entry}")
        return
    python = sys.executable
    print(f"启动脚本(GUI): {python} {bot_entry}")
    subprocess.Popen([python, bot_entry])


def main():
    parser = argparse.ArgumentParser(description="启动剑与远征：启程，并可联动启动本项目脚本")
    parser.add_argument("--bot", action="store_true", help="启动游戏后同时启动本项目脚本(GUI)")
    parser.add_argument("--delay", type=int, default=3, help="--bot 时，启动游戏后等待多少秒再启脚本（默认 3）")
    args = parser.parse_args()

    launched = launch_game()

    if args.bot:
        if launched is None:
            print("（未成功启动游戏，仍按请求启动脚本）")
        else:
            print(f"等待 {args.delay} 秒让游戏启动…")
            time.sleep(max(0, args.delay))
        launch_bot()


if __name__ == "__main__":
    main()
