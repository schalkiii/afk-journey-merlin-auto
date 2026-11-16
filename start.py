"""启动任务模块：登录游戏并清理开局弹窗。

被「运行登录」功能调用。逻辑分四阶段：
1. 等游戏窗口出现且画面不再是加载态（冷启动时这一步最容易被跳过，后果也最大）；
2. 等待开始界面点击 start 进入游戏；若游戏已越过开始界面（月卡/礼包或可交互弹窗）则跳过；
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
    click_position,
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


def _click_start_with_confirm(start_path, attempts=3):
    """点击 start 并校验界面真的离开开始界面；没离开就补点，最多 attempts 轮。

    2026-11-16 定时实测：注入器未启动时 `send_coord` 前两次未消费是静默的，而
    `wait_and_click` 只看「模板命中 + 坐标已写」就返回 True——于是 start 点击落空
    却被当成「已进入」，登录白等两分半、游戏始终停在「点击开始游戏」。

    这里按「点击 → 轮询确认 start 消失 → 未生效补点」来判，与
    `common.click_and_confirm` 同构；每次只点一下（twice=False），避免跳转型按钮
    连点造成「进入后又退出」。返回 True 表示确认已进入（start 消失且加载完成）。
    """
    for attempt in range(1, attempts + 1):
        pos = _find(start_path)
        if pos is None:
            # 没找到 start：要么上一次点击已生效，要么游戏正在切场景。
            # 等加载结束再看是否落到主界面/弹窗，避免把加载误判成失败。
            wait_until_loaded(20.0)
            if (at_main_interface()
                    or _find(get_template_path("dianjikongbaichuguanbi.png"))
                    or _find(get_template_path("yuekajiangli.png"))
                    or _find(get_template_path("libao.png"))):
                log("start 已消失且已进入游戏/弹窗，视为点击生效")
                return True
            log(f"第 {attempt} 轮未找到 start，也未确认进入游戏，继续尝试")
            continue

        log(f"点击 start（第 {attempt}/{attempts} 次），坐标 {pos}")
        click_position(pos, wait=0.6, twice=False)

        # 轮询确认 start 消失（点击生效后页面必然离开开始界面）
        deadline = time.time() + 8.0
        left_start = False
        while time.time() < deadline:
            if _find(start_path) is None:
                left_start = True
                break
            time.sleep(0.5)
        if left_start:
            log("start 点击已生效，等待加载完成")
            wait_until_loaded(20.0)
            return True
        log(f"第 {attempt} 次点击 start 后仍停在开始界面，补点")

    log(f"连续 {attempts} 次点击 start 后仍停在开始界面，登录流程放弃")
    return False


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
            return _click_start_with_confirm(start_path)
        # 2026-11-16 实机：冷启动可能已越过 start 界面，直接停在
        # 「点击空白处关闭」弹窗上（wait_for_game_ready 已按 GAME_READY_MARKERS
        # 把它判为「可交互」）。旧实现只认 start/月卡/礼包/主界面，于是每轮
        # 都落空、白等满 180 秒才误判登录失败，后续任务跟着在错界面连败。
        # 弹窗说明已经越过开始界面，交给 _dismiss_popups 清理即可。
        if _find(get_template_path("dianjikongbaichuguanbi.png")):
            log("检测到可交互弹窗（已越过开始界面），转弹窗清理")
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
