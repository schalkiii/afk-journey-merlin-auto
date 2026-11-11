"""翻翻乐：自动点「点击增加进度」把钥匙烧完。

实测机制（2026-11-04，客户区 1600×900）：
- **一次单击不是 +1，而是连抽到本轮 100 满为止**：进度 54/100 时点一次，钥匙 265→219（−46）、
  进度归 0；再点一次，钥匙 219→119（−100）。所以「点一次=跑满一轮」，不需要长按——
  此前怀疑要长按，是判据选错：进度数字每轮归零，看起来像「点了没反应」，
  真正单调变化的是**钥匙余量**。
- 翻卡与里程碑奖励都是**静默入账**，没有「获得奖励」弹窗，所以成败只能靠钥匙余量判断。
- 单击生效前必须已激活窗口（common.ensure_game_clickable 内含 0.25s 等待），
  且这里只能用 `twice=False`：连点两下会白烧一整轮钥匙。

钥匙是钓鱼等玩法产出、且每周结算清零，烧掉才是本活动的目的，因此默认把余量点空。
"""

import time

from common import (
    check_stop,
    click_position,
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

tpl_menu = get_template_path("caidan.png")
tpl_task_tab = get_template_path("renwu.png")
tpl_fanfanle_tab = get_template_path("fanfanle.png")
tpl_fanfanle_tab_selected = get_template_path("fanfanle2.png")
tpl_add_progress = get_template_path("zengjiajindu.png")

# 「当前剩余：🔑NNN」数字条在客户区的位置，用于点击前后的变化比对
KEYS_REGION = (760, 762, 150, 28)
# 「累计进度：NNN/100」进度条：每轮点完都会归零重算，数字变化比钥匙余量更显眼。
# 2026-11-10 实机教训：只盯「当前剩余」这一行时，连续三轮点击都报「钥匙余量未变化」，
# 而实际钥匙 157 → 0 全烧完了——判据太窄，任一处变化都应算这一轮点进去了。
PROGRESS_REGION = (740, 660, 160, 34)
# 实测噪声底：稳定帧自匹配 1.000，但**刚进页面的过渡动画期间会掉到 0.964–0.975**。
# 阈值必须落在噪声带之下，否则页面还没停稳就会被判成「钥匙变了」，空烧也当成功。
# 数字真变化时分数远低于此（进度区域同法实测掉到 0.428）。
KEYS_CHANGED_BELOW = 0.90

# 单次运行最多跑几轮（每轮最多烧 100 把钥匙，留个上限防意外）
DEFAULT_MAX_ROUNDS = 10
MAX_ROUNDS_LIMIT = 50

# 2026-11-11 实机：一轮点完有翻牌结算演出，演出期间再点不生效，旧实现把「点了没变化」
# 直接当成「钥匙已用完」——当天钥匙还剩 376 把就报「完成 1 轮、钥匙用完」。
# 现在每轮开始先等演出停稳取基准帧，点一次没变化就重试；连续多次都不变化才判用完。
ROUND_SETTLE = 2.5
CLICK_RETRIES = 3


def _region_crop(region):
    """取客户区某个相对区域的图像。"""
    x, y, _w, _h = game_client_region()
    frame = screenshot_bgr()
    lx, ly, lw, lh = region
    return frame[y + ly:y + ly + lh, x + lx:x + lx + lw]


def _keys_region_crop():
    """取当前钥匙余量区域的图像。"""
    return _region_crop(KEYS_REGION)


def _enter_fanfanle():
    """主界面 → 菜单 → 任务 → 翻翻乐页签，并用「点击增加进度」按钮确认进来了。"""
    if not wait_and_click(tpl_menu, "菜单", 0.8, timeout=5.0):
        log("未找到主界面「菜单」入口。")
        return False
    if not wait_and_click(tpl_task_tab, "任务", 0.8, timeout=5.0):
        log("菜单里没有「任务」入口。")
        recover_to_main_interface()
        return False

    # 2026-11-10 实机：点完「任务」后面板可能根本没打开（点击被弹框吞掉 / 加载慢），
    # 旧实现直接找页签，找不到就误报「任务面板里没有翻翻乐页签」（现场截图停在主界面）。
    # 先用底部页签栏确认面板打开，未打开则补点一次「任务」。
    from hongbaolingqu import _panel_open

    if not _panel_open():
        log("点「任务」后未确认任务面板打开，补点一次「任务」")
        if not wait_and_click(tpl_task_tab, "任务(补点)", 0.8, timeout=5.0):
            log("补点「任务」失败，判定没进入任务面板。")
            recover_to_main_interface()
            return False
        if not _panel_open():
            log("补点后任务面板仍未打开，判定没进入。")
            recover_to_main_interface()
            return False

    # 页签有选中/未选中两套外观，任一命中都点（已选中时重复点无害）。
    # 面板打开有延迟，这里必须带超时重试，否则刚点完「任务」就找页签会扑空。
    # 2026-11-10 实机：fanfanle.png 是从别的背景裁的 45x16 小图，任务面板停在别的页签
    # （未选中态）时只到 0.72，选中态反而有 0.93——顺序改成先认选中态。两套模板现在
    # 分别对应选中/未选中外观（未选中态已按实机重采）。
    tab_pos = (find_center_silent(tpl_fanfanle_tab_selected, 0.8, timeout=4.0)
               or find_center_silent(tpl_fanfanle_tab, 0.8, timeout=2.0))
    if tab_pos is None:
        log("任务面板里没有「翻翻乐」页签。")
        recover_to_main_interface()
        return False

    # 点页签后如果没出现按钮，多半是这一次点击被吞（或切页动画没走完），重找页签再点一次
    for attempt in range(1, 3):
        click_position(tab_pos, wait=2.0, twice=False)
        if find_center_silent(tpl_add_progress, threshold=0.8, timeout=4.0) is not None:
            time.sleep(0.8)
            return True
        log(f"第 {attempt} 次点「翻翻乐」页签后没看到「点击增加进度」按钮")
        tab_pos = (find_center_silent(tpl_fanfanle_tab_selected, 0.8, timeout=2.0)
                   or find_center_silent(tpl_fanfanle_tab, 0.8, timeout=1.0))
        if tab_pos is None:
            break

    log("点进翻翻乐后没看到「点击增加进度」按钮，判定没进入。")
    recover_to_main_interface()
    return False


def _wait_keys_change(before_keys, before_progress, timeout=6.0):
    """等待「钥匙余量」或「累计进度」任一区域与点击前不再一致。

    数字有滚动动画，只读一次会误判成没变化；两处都看是为了避免 2026-11-10 那种
    「钥匙确实烧完了、脚本却说没变化」的窄判据误报。超时放宽到 6 秒，覆盖一期
    翻牌动画（100 把钥匙的结算演出）。
    """
    deadline = time.time() + timeout
    while True:
        if region_changed_since(before_keys, KEYS_REGION,
                                threshold=KEYS_CHANGED_BELOW, timeout=0):
            return True
        if region_changed_since(before_progress, PROGRESS_REGION,
                                threshold=KEYS_CHANGED_BELOW, timeout=0):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.4)


def burn_keys(max_rounds=DEFAULT_MAX_ROUNDS):
    """反复点「点击增加进度」直到钥匙烧完或到达轮次上限，返回成功推进的轮数。"""
    burned = 0
    for attempt in range(1, max_rounds + 1):
        check_stop()
        # 上一轮（若有）的翻牌结算演出还没停稳时，基准帧本身就是动画帧，之后的比对
        # 既可能把「没点动」看成变化，也可能把「点动了」看成没变化。先等演出结束。
        time.sleep(ROUND_SETTLE)
        before_keys = _keys_region_crop()
        before_progress = _region_crop(PROGRESS_REGION)
        progressed = False
        for retry in range(1, CLICK_RETRIES + 1):
            button_pos = find_center_silent(tpl_add_progress, 0.8)
            if button_pos is None:
                log(f"第 {attempt} 轮没找到「点击增加进度」按钮，结束。")
                return burned
            click_position(button_pos, wait=2.0, twice=False)
            invalidate_screenshot_cache()
            if _wait_keys_change(before_keys, before_progress):
                progressed = True
                break
            log(f"第 {attempt} 轮第 {retry} 次点击后钥匙余量/累计进度未变化，"
                "可能是结算演出未结束，重试")
            # 重试前把基准帧刷新到当前画面，避免拿旧基准反复比同一段动画
            time.sleep(ROUND_SETTLE)
            invalidate_screenshot_cache()
            before_keys = _keys_region_crop()
            before_progress = _region_crop(PROGRESS_REGION)
        if not progressed:
            log(f"连续 {CLICK_RETRIES} 次点击都没让钥匙余量变化，判定钥匙已用完，停止。")
            break
        burned += 1
        log(f"第 {attempt} 轮已推进（钥匙余量 / 累计进度有变化）。")
    return burned


def main(max_rounds=DEFAULT_MAX_ROUNDS):
    """进入翻翻乐并把钥匙烧掉。返回 True=进入了并执行，False=没能进入。"""
    log("开始执行翻翻乐...")
    recover_to_main_interface()
    if not _enter_fanfanle():
        return False

    rounds = max(1, min(int(max_rounds), MAX_ROUNDS_LIMIT))
    burned = burn_keys(rounds)
    log(f"翻翻乐：完成 {burned} 轮推进（上限 {rounds} 轮）。")

    recover_to_main_interface()
    return True


if __name__ == "__main__":
    main()
