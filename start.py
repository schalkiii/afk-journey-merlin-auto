"""启动任务模块：登录游戏并清理开局弹窗。

被「运行登录」功能调用。逻辑分四阶段：
1. 等游戏窗口出现且画面不再是加载态（冷启动时这一步最容易被跳过，后果也最大）；
2. 等待开始界面点击 start 进入游戏；若游戏已越过开始界面（直接出现月卡/礼包）则跳过；
3. 循环处理月卡奖励、礼包与「点击空白处关闭」类弹窗，直到连续一段时间无弹窗；
4. 确认已经落在主界面，返回是否真的登录成功。

2026-11-12 实机：定时冷启动时 GUI 只按固定 20 秒就开始跑任务，游戏仍在登录/资源校验
画面上，于是第一个任务「邮件」在开始界面找「菜单」15 秒超时失败，后面十几项连败。
本模块因此把「等窗口 / 等开始界面 / 等主界面」三段的超时都放宽，并把结果如实返回——
旧实现恒返回成功，从日志上看不出「其实根本没进游戏」。
"""

import time

from common import (
    at_main_interface,
    get_template_path,
    log,
    wait_and_click,
    wait_for_game_ready,
    wait_until_loaded,
)

# 各阶段等待/空闲阈值（秒）
GAME_READY_TIMEOUT = 90      # 进入本任务前等游戏窗口就绪的上限（GUI 通常已等过）
START_WAIT_TIMEOUT = 180     # 开始界面最长等待时间：冷启动实测可达 1 分半以上
LOGIN_READY_TIMEOUT = 120    # 点完 start 后等主界面的上限
POPUP_IDLE_TIMEOUT = 30      # 连续无弹窗多久即判定启动完成
POPUP_MAX_ROUNDS = 30        # 弹窗处理轮数上限：点不掉的弹窗不能把登录流程挂死


def _find(template_path, threshold=0.8, timeout=0):
    """静默查找模板；命中返回坐标，否则 None。"""
    from common import find_center_silent

    return find_center_silent(template_path, threshold, timeout=timeout)


def _wait_for_start(start_path, yuekajiangli_path, libao_path, timeout=START_WAIT_TIMEOUT):
    """等待开始界面并点击 start 进入游戏。

    若游戏已越过开始界面（月卡/礼包直接出现），视为 start 已被点过，直接跳过。
    已经在主界面同样视为「不需要点开始」（游戏可能是热重启，登录态还在）。
    返回 True 表示已处理（点击或跳过），False 表示超时未出现。
    """
    deadline = time.time() + timeout
    last_note = 0.0
    while time.time() < deadline:
        # 游戏已越过开始界面：月卡/礼包直接出现，无需再点 start
        if _find(yuekajiangli_path) or _find(libao_path):
            log("检测到月卡/礼包界面，视为已开始，跳过 start")
            return True
        if at_main_interface():
            log("已在主界面，无需点 start")
            return True
        if _find(start_path):
            log("检测到 start，点击进入")
            wait_and_click(start_path, "start")
            time.sleep(2)
            wait_until_loaded(30.0)
            return True
        now = time.time()
        if now - last_note >= 15.0:
            last_note = now
            log(f"等待开始界面…（剩余 {int(deadline - now)} 秒）")
        time.sleep(0.5)
    return False


def _dismiss_popups(yuekajiangli_path, libao_path, tuichulibao_path, idle_timeout=POPUP_IDLE_TIMEOUT):
    """循环点击月卡奖励、礼包与通用「点击空白处关闭」弹窗，直到连续 idle_timeout 秒无弹窗。

    轮数上限 `POPUP_MAX_ROUNDS`：正常冷启动弹窗 3-8 个，30 轮足够；一旦某个弹窗
    点不掉（模板与画面错位、奖励动画卡住），没有上限就会在这里无限循环，
    表现是「登录任务一直不结束」而不是「报错」——比直接失败更难诊断。
    """
    hint_path = get_template_path("dianjikongbaichuguanbi.png")
    last_seen = time.time()
    rounds = 0
    while True:
        if rounds >= POPUP_MAX_ROUNDS:
            log(f"弹窗处理已达 {POPUP_MAX_ROUNDS} 轮上限，停止清理并按当前界面继续")
            break
        if _find(yuekajiangli_path):
            wait_and_click(yuekajiangli_path, "yuekajiangli")
            time.sleep(2)
            last_seen = time.time()
            rounds += 1
        elif _find(libao_path):
            # 礼包弹窗的关闭按钮是 tuichulibao 模板，而非 libao 本身
            wait_and_click(tuichulibao_path, "tuichulibao")
            time.sleep(2)
            last_seen = time.time()
            rounds += 1
        elif _find(hint_path):
            # 冷启动还会叠公告 / 活动 / 新手礼包这类弹窗，它们没有专门的模板，
            # 但都带「点击空白处关闭」提示——不处理就会一直挡着主界面，后面首个任务失败。
            wait_and_click(hint_path, "dianjikongbaichuguanbi(登录弹窗)")
            time.sleep(1.5)
            last_seen = time.time()
            rounds += 1
        elif time.time() - last_seen >= idle_timeout:
            log(f"连续 {idle_timeout} 秒未检测到弹窗，启动完成")
            break
        time.sleep(0.5)


def main():
    """启动任务入口：登录并清理开局弹窗。返回是否已确认落在主界面。"""
    log("开始执行启动任务...")
    # 统一走 get_template_path：它会用 APPDATA 下的模板副本，避免打包后 _MEIPASS
    # 被清理/隔离时本任务单独找不到模板（其余任务早已如此）
    start_path = get_template_path("start.png")
    yuekajiangli_path = get_template_path("yuekajiangli.png")
    libao_path = get_template_path("libao.png")
    tuichulibao_path = get_template_path("tuichulibao.png")

    status, msg = wait_for_game_ready(timeout=GAME_READY_TIMEOUT)
    log(f"游戏就绪检查: {msg}")
    if status == "no_window":
        log("游戏窗口不存在，登录流程无法继续")
        return False

    if not _wait_for_start(start_path, yuekajiangli_path, libao_path):
        log(f"{START_WAIT_TIMEOUT} 秒内既没看到开始界面也没到主界面，登录流程放弃")
        return False

    _dismiss_popups(yuekajiangli_path, libao_path, tuichulibao_path)

    # 最后确认：弹窗清完必须真的在主界面，否则后续 18 项任务全部会在错位界面上失败
    deadline = time.time() + LOGIN_READY_TIMEOUT
    while time.time() < deadline:
        if at_main_interface():
            log("启动任务执行完成：已确认位于主界面")
            return True
        if _find(get_template_path("dianjikongbaichuguanbi.png")):
            wait_and_click(get_template_path("dianjikongbaichuguanbi.png"),
                           "dianjikongbaichuguanbi(收尾弹窗)")
        time.sleep(1.0)
    log(f"{LOGIN_READY_TIMEOUT} 秒内仍未确认主界面，登录流程按未完成处理")
    return False


if __name__ == "__main__":
    main()
