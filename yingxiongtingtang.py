"""英雄厅堂：自动点「快速升级」提升赛季共鸣等级。

实测：点一次「快速升级」立刻 +1 级（650→651→652→653），全员等级与总战力同步上升，
**既没有确认弹窗也没有「获得奖励」弹窗**，所以不能靠弹窗判断成败。改用「等级数字区域
点击前后的模板自匹配分」：静止时连续四帧稳定 1.000，升级后掉到 0.918–0.943，
阈值取 0.97 即可区分。

不自动处理「初识之人」红点：那是公会结社科技树（万星结社 / 弑律 / 律法），实测进入后
底部「升级」是灰的（共鸣资源 980/2000 不足），而且选哪个节点会决定公会玩法加成的方向，
属于要人决策的项，不替用户点。
"""

import time

from common import (
    check_stop,
    find_center_silent,
    game_client_region,
    get_template_path,
    invalidate_screenshot_cache,
    log,
    recover_to_main_interface,
    region_changed_since,
    screenshot_bgr,
    wait_and_click,
)

tpl_hero_hall_tab = get_template_path("yingxiongtingtang_tab.png")
tpl_quick_upgrade = get_template_path("kuaisushengji.png")

# 「赛季共鸣等级：NNN」里数字区域在客户区的位置，用于点击前后的变化比对
LEVEL_REGION = (862, 283, 56, 30)
# 等级没变时自匹配稳定在 1.0；升一级会掉到 0.92–0.94
LEVEL_CHANGED_BELOW = 0.97

# 单次运行最多点几次快速升级（每级都要吃共鸣资源，不能无限点）
DEFAULT_QUICK_UPGRADE_TIMES = 10
MAX_QUICK_UPGRADE_TIMES = 99


def _level_region_crop():
    """取当前等级数字区域的图像。"""
    x, y, _w, _h = game_client_region()
    frame = screenshot_bgr()
    lx, ly, lw, lh = LEVEL_REGION
    return frame[y + ly:y + ly + lh, x + lx:x + lx + lw]


def _enter_hero_hall():
    """从主界面进入英雄厅堂，并用「快速升级」按钮确认确实进来了。"""
    if not wait_and_click(tpl_hero_hall_tab, "英雄厅堂页签", 0.8, timeout=5.0):
        log("未找到主界面底部「英雄厅堂」入口。")
        return False
    if not find_center_silent(tpl_quick_upgrade, threshold=0.8, timeout=3.0):
        log("点击英雄厅堂后未看到「快速升级」按钮，判定没进入。")
        recover_to_main_interface()
        return False
    time.sleep(0.8)
    return True


def _wait_level_change(before, timeout=3.0):
    """等待等级区域与点击前不再一致；升级数字有跳字动画，只读一次会误判成没变化。"""
    return region_changed_since(
        before, LEVEL_REGION, threshold=LEVEL_CHANGED_BELOW, timeout=timeout
    )


def quick_upgrade(times=DEFAULT_QUICK_UPGRADE_TIMES):
    """在英雄厅堂反复点「快速升级」，直到点不动或达到次数上限。返回成功升级次数。"""
    upgraded = 0
    for attempt in range(1, times + 1):
        check_stop()
        before = _level_region_crop()
        if not wait_and_click(tpl_quick_upgrade, f"kuaisushengji({attempt})", 0.8, timeout=2.0):
            log(f"第 {attempt} 次没找到「快速升级」按钮，结束升级。")
            break
        invalidate_screenshot_cache()
        if _wait_level_change(before):
            upgraded += 1
        else:
            log("点击 3 秒后等级仍未变化（共鸣资源可能不足），停止升级。")
            break
    return upgraded


def main(quick_upgrade_times=DEFAULT_QUICK_UPGRADE_TIMES):
    """进入英雄厅堂并自动快速升级。返回 True=进入了并执行，False=没能进入。"""
    log("开始执行英雄厅堂快速升级...")
    recover_to_main_interface()
    if not _enter_hero_hall():
        return False

    times = max(1, min(int(quick_upgrade_times), MAX_QUICK_UPGRADE_TIMES))
    upgraded = quick_upgrade(times)
    log(f"英雄厅堂：快速升级成功 {upgraded} 级（上限 {times} 次）。")

    recover_to_main_interface()
    return True


if __name__ == "__main__":
    main()
