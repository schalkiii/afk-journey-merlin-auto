"""红点奖励领取：把界面上「可领取」的奖励点掉，最后回到主界面。

覆盖：
1. 「菜单 → 任务」面板：每日任务 / 公会任务 / 成长挑战 / 赛季任务（二级玩法页 +
   底部三个阶段页）/ 家园目标，用「一键领取」与单个「领取」；
2. 主界面「赛季手册 → 赛季里程碑」的一键领取；
3. 主界面右侧「赛季月桂之旅」，逐个底部手记页签一键领取；
4. 主界面「当前进度 → 赛季挂机关卡」：右上角挂机收益 + 里程碑节点（该页没有
   一键领取，逐节点试点，只把弹出奖励的算作领取）。

不覆盖，且都有实测依据：
- 翻翻乐：不是红点，而是**消耗钥匙换进度**的玩法，已单独成模块 `fanfanle.py`。
  （本文件最初记的「点 3 次进度仍 0/100、机制未确认」是判据选错：进度数字每满 100 归零，
  真正单调变化的是钥匙余量——实测一次单击会连抽到本轮 100 满。）
- 「玩法目录 → 活动 / 公会玩法」的卡片列表：曾按固定栅格逐张盲点，实测会误闯
  「纷战争锋」这类带自动派遣的活动页，且各页返回箭头素材不统一、恢复不可靠，已撤销；
  这些玩法本身已有专门模块（结社战线、狩猎悬赏）；
- 背包 / 图鉴 / 旅行指南等「新」角标：新内容提示，没有可领奖励。
"""

import time

import cv2

from common import (
    BOTTOM_BAR_CLIENT_REGION,
    at_main_interface,
    check_stop,
    click_blank_to_exit,
    click_position,
    crops_differ,
    find_center_silent,
    game_client_region,
    get_cached_screenshot,
    get_template_path,
    invalidate_screenshot_cache,
    load_template,
    log,
    recover_to_main_interface,
    tap_hud_entry,
    wait_and_click,
)

tpl_caidan = get_template_path("caidan.png")
tpl_renwu = get_template_path("renwu.png")
tpl_richangrenwu_tab = get_template_path("richangrenwutab.png")
tpl_gonghuirenwu = get_template_path("gonghuirenwu.png")
tpl_chengzhang = get_template_path("chengzhangtiaozhan.png")
tpl_saijirenwu = get_template_path("saijirenwu.png")
tpl_jiayuan = get_template_path("jiayuanmubiao.png")
tpl_wanfa = get_template_path("wanfa.png")
tpl_jieduaimubiao = get_template_path("jieduaimubiao.png")
tpl_saijichengzhang = get_template_path("saijichengzhangrenwu.png")
tpl_saijijieduan = get_template_path("saijijieduan.png")
tpl_yijianlingqu = get_template_path("yijianlingqu.png")
tpl_lingqu = get_template_path("lingqu.png")
tpl_blank_close = get_template_path("dianjikongbaichuguanbi.png")
# 赛季手册入口用不透明的图标本体：文字标签是半透明药丸，镜头换场景后
# 背景透光会让匹配从 1.0 掉到 0.767（实测），图标带流光也还有 0.965。
tpl_saijishouchuo = get_template_path("saijishouchuoicon.png")
SEASON_BOOK_THRESHOLD = 0.85
tpl_saijilichengbei = get_template_path("saijilichengbei.png")
# 任务面板底部页签栏（未选中态灰字）。面板会记住上次停留的页签，选中态会变绿
# （实测 fanfanle 选中后只剩 0.724 分），因此「面板已打开」用多页签或判断。
PANEL_TAB_TEMPLATES = (
    tpl_richangrenwu_tab,
    tpl_chengzhang,
    tpl_saijirenwu,
    tpl_jiayuan,
)

# 面板左下角返回箭头：实测任务面板/赛季手册用的是 exitck 这套外观，
# 玩法目录的 exit.png 与菜单的 fanhui.png 在这里都只有 0.42 分，匹配不到。
tpl_panel_back = get_template_path("exitck.png")
# 但同类箭头在不同面板用的是不同素材：玩法目录列表 / 任务面板 / 赛季手册是 exitck，
# 活动与公会卡片详情页是 fanhui（实测 exitck 在详情页只有 0.283）。返回时按候选依次试。
tpl_fanhui = get_template_path("fanhui.png")
PANEL_BACK_TEMPLATES = (tpl_panel_back, tpl_fanhui)


# 主界面右侧竖排的「赛季月桂之旅」入口图标位置，与进入后的底部手记页签栅格
LAUREL_HUD_POS = (1550, 610)
LAUREL_CAROUSEL_SLOTS = [(480, 845), (630, 845), (780, 845), (880, 845), (990, 845)]

# 赛季挂机关卡页右上角的「x440」挂机收益按钮（实测点击即弹「获得奖励」）
IDLE_REWARD_POS = (1120, 240)

# 页面中部的产出宝箱（满箱金光态）与点开后弹出的「收获奖励」按钮
tpl_baoxiang_full = get_template_path("baoxiang_full.png")
tpl_shouhuojiangli = get_template_path("shouhuojiangli.png")

# 赛季挂机关卡里程碑轨道上的未解锁节点（灰色瓶子），用于取节点行的 y
tpl_milestone_locked = get_template_path("guajiguajia_locked.png")
MILESTONE_ROW_Y_FALLBACK = 349

# 主界面「当前进度」入口：HUD 上的仓鼠位置（半透明标签与脉动角标都不能做模板，
# 客户区固定 1600x900 下直接点该位置，再用里程碑轨道锚点校验是否真的进了面板）
PROGRESS_HUD_POS = (72, 833)
# 主界面左下角「目标」是任务面板的**直达入口**（实测客户区 (35,747)，有可领时带红色「!」）。
# 菜单→任务 要连中 caidan、renwu 两处模板，任一处失效就进不了面板；这条只点一次的兜底
# 路径少一层依赖，作为失败后的第二选择。
TASK_PANEL_HUD_POS = (35, 747)
MILESTONE_TRACK_REGION = (400, 320, 880, 60)

# 里程碑节点间距实测 54px，最左节点中心在 x=432
MILESTONE_X_START = 432
MILESTONE_X_STEP = 54
MILESTONE_X_END = 1250

MAX_MILESTONE_CLICKS = 16

# 赛季任务的二级页签（玩法 / 活跃 / 限时 / 养成 / 剧情）等宽排列，
# 以「玩法」命中位置为基准横向偏移，避免为每个页签单独存一份模板。
SEASON_SUB_TAB_OFFSET_X = [0, 132, 264, 397, 532]

# 单个界面最多点击多少次领取（防止领取后界面不刷新导致死循环）
MAX_CLAIM_PER_VIEW = 30

# 单个界面首轮给「一键领取」的宽限：页面刚打开时按钮可能还在加载
YIJIAN_FIRST_TIMEOUT = 1.0

# 确认任务面板已打开的总窗口与轮询间隔：每轮在同一帧上检查全部页签模板，
# 只有整轮都没命中才等待下一帧（原实现 4 个模板各等 1s，未打开时最坏约 4s）
PANEL_OPEN_TIMEOUT = 2.0
PANEL_POLL_INTERVAL = 0.3

# 进入任务面板的重试次数
ENTRY_RETRY = 2


def _click_panel_back(name):
    """按候选素材依次尝试返回箭头，命中即点。"""
    for template in PANEL_BACK_TEMPLATES:
        if wait_and_click(template, f"back({name})", 0.8, timeout=1.0):
            return True
    log(f"未找到返回箭头，无法退出{name}。")
    return False


def _close_reward_popup():
    """领取后若弹出「获得奖励」，点空白关闭。"""
    if find_center_silent(tpl_blank_close, threshold=0.8, timeout=1.0):
        click_blank_to_exit()
        time.sleep(0.8)
        return True
    return False


def claim_current_view():
    """在当前界面反复点击「一键领取」与单个「领取」，直到两者都不再出现。

    先点一键领取：单个「领取」模板带勾选圆标，与一键领取按钮外观不同，
    两者互不误命中，因此顺序只影响次数，不影响正确性。
    """
    clicked = 0
    round_index = 0
    while clicked < MAX_CLAIM_PER_VIEW:
        check_stop()
        # 首轮留宽限等页面加载；一键领取要么一直在、要么本轮已确认不在，
        # 单点「领取」不会让它新出现，后续轮次不再白等
        yijian_timeout = YIJIAN_FIRST_TIMEOUT if round_index == 0 else 0
        round_index += 1
        if wait_and_click(tpl_yijianlingqu, "yijianlingqu", 0.8, timeout=yijian_timeout):
            clicked += 1
            _close_reward_popup()
            continue

        pos = find_center_silent(tpl_lingqu, threshold=0.8, timeout=0.5)
        if not pos:
            break
        click_position(pos, wait=1.0, twice=False)
        clicked += 1
        _close_reward_popup()

    if clicked >= MAX_CLAIM_PER_VIEW:
        log(f"单个界面领取点击达到上限 {MAX_CLAIM_PER_VIEW} 次，跳过当前界面。")
    return clicked


def _panel_open():
    """底部页签栏里任意一个未选中页签可见，即认为任务面板已打开。

    每轮在同一帧上依次检查 4 个页签模板（timeout=0 只匹配一次，复用截图缓存），
    整轮都没命中才等一个轮询间隔再取下一帧，直到 PANEL_OPEN_TIMEOUT。
    这样面板没打开时不会逐个模板各白等 1s。
    """
    deadline = time.time() + PANEL_OPEN_TIMEOUT
    while True:
        for template in PANEL_TAB_TEMPLATES:
            if find_center_silent(template, threshold=0.8, timeout=0,
                                  client_region=BOTTOM_BAR_CLIENT_REGION):
                return True
        if time.time() >= deadline:
            return False
        check_stop()
        time.sleep(PANEL_POLL_INTERVAL)


def _open_task_panel_via_menu():
    """菜单 -> 任务，用底部页签栏确认面板已打开。

    重试时必须先判断是否已经停在菜单里：菜单打开后 HUD 上的 caidan 按钮就消失了，
    照着原样再点一次菜单只会白等一轮（实测第 2 次尝试因此两处都找不到）。
    """
    for attempt in range(1, ENTRY_RETRY + 1):
        check_stop()
        if not find_center_silent(tpl_renwu, threshold=0.8, timeout=1.0) and not wait_and_click(
            tpl_caidan, f"caidan({attempt})", 0.8, timeout=5.0
        ):
            log(f"第 {attempt} 次未找到菜单入口 caidan。")
            continue
        if not wait_and_click(tpl_renwu, f"renwu({attempt})", 0.8, timeout=5.0):
            log(f"第 {attempt} 次点击菜单后未找到任务入口 renwu。")
            continue
        if _panel_open():
            time.sleep(0.8)
            return True
        log(f"第 {attempt} 次点击任务后未确认进入任务面板（底部页签栏缺失）。")
    return False


def _open_task_panel_via_hud():
    """兜底入口：主界面左下角「目标」直达任务面板（少一层菜单模板依赖）。

    角落 HUD 图标在窗口未前台时，第一次点击会被系统当成激活点击吞掉——实测
    twice=False 点它完全没有反应，改 twice=True 立刻进得去，所以这里连点两下，
    并且每次都再用页签栏确认，不靠「点了就当进去了」。
    """
    def click(corner_pos):
        region = game_client_region()
        click_position(
            (region[0] + corner_pos[0], region[1] + corner_pos[1]), wait=2.0, twice=True
        )

    if not tap_hud_entry(
        TASK_PANEL_HUD_POS,
        _panel_open,
        retries=ENTRY_RETRY,
        click=click,
        log_func=lambda attempt: log(f"第 {attempt} 次点「目标」后未见任务面板页签栏。"),
    ):
        return False
    log("经主界面「目标」入口进入任务面板。")
    time.sleep(0.8)
    return True


def _open_task_panel():
    """先进任务面板：菜单路径优先，失败再用主界面「目标」直达入口兜底。"""
    if _open_task_panel_via_menu():
        return True
    log("菜单 → 任务 没能打开面板，改用主界面左下角「目标」直达入口。")
    return _open_task_panel_via_hud()


def _sweep_view(name):
    count = claim_current_view()
    log(f"红点领取：{name} 领取 {count} 项。")
    return count


def _sweep_season_task_tab():
    """赛季任务：当前视图 + 二级玩法页 + 底部三个阶段页。"""
    total = _sweep_view("赛季任务")

    anchor = find_center_silent(tpl_wanfa, threshold=0.8, timeout=1.5)
    if anchor:
        for offset_x in SEASON_SUB_TAB_OFFSET_X:
            check_stop()
            click_position((anchor[0] + offset_x, anchor[1]), wait=1.0, twice=False)
            total += _sweep_view(f"赛季任务-二级页(偏移 {offset_x})")
    else:
        log("赛季任务未识别到「玩法」二级页签，跳过二级页遍历。")

    for template, stage_name in (
        (tpl_jieduaimubiao, "阶段目标"),
        (tpl_saijichengzhang, "赛季成长任务"),
        (tpl_saijijieduan, "赛季阶段"),
    ):
        check_stop()
        if not wait_and_click(template, f"赛季任务-{stage_name}", 0.8, timeout=2.0,
                              client_region=BOTTOM_BAR_CLIENT_REGION):
            log(f"未找到赛季任务底部页签「{stage_name}」，跳过。")
            continue
        total += _sweep_view(f"赛季任务-{stage_name}")
    return total


def _claim_task_panel():
    """任务面板各页签依次领取。返回领取总数。"""
    total = 0
    # 面板会停在上次浏览的页签，先显式点回每日任务，避免漏扫
    if wait_and_click(tpl_richangrenwu_tab, "richangrenwutab", 0.8, timeout=3.0,
                      client_region=BOTTOM_BAR_CLIENT_REGION):
        time.sleep(0.8)
    total += _sweep_view("每日任务")

    if wait_and_click(tpl_gonghuirenwu, "gonghuirenwu", 0.8, timeout=2.0,
                      client_region=BOTTOM_BAR_CLIENT_REGION):
        total += _sweep_view("公会任务")
    else:
        log("未找到公会任务页签，跳过。")

    for template, tab_name in (
        (tpl_chengzhang, "成长挑战"),
        (tpl_saijirenwu, "赛季任务"),
        (tpl_jiayuan, "家园目标"),
    ):
        check_stop()
        if not wait_and_click(template, f"页签 {tab_name}", 0.8, timeout=3.0,
                              client_region=BOTTOM_BAR_CLIENT_REGION):
            log(f"未找到任务面板页签「{tab_name}」，跳过。")
            continue
        if tab_name == "赛季任务":
            total += _sweep_season_task_tab()
        else:
            total += _sweep_view(tab_name)
    return total


def _claim_season_book(icon_pos):
    """主界面「赛季手册」图标 → 赛季里程碑页的一键领取。"""
    click_position(icon_pos, wait=1.5, twice=False)
    if not find_center_silent(tpl_saijilichengbei, threshold=0.8, timeout=3.0):
        log("点击赛季手册后未确认进入赛季里程碑界面，跳过。")
        _click_panel_back("赛季手册")
        return 0
    count = _sweep_view("赛季手册-赛季里程碑")
    _click_panel_back("赛季手册")
    return count


def _find_all_matches(template_path, threshold, client_region):
    """在客户区子区域内枚举模板的全部命中中心（返回整屏绝对坐标）。

    find_center_silent 只给最优命中；里程碑轨道要一次看到全部节点位置。
    """
    win_x, win_y, _w, _h = game_client_region()
    region_x, region_y, region_w, region_h = client_region
    left, top = win_x + region_x, win_y + region_y
    area = get_cached_screenshot()[top:top + region_h, left:left + region_w]

    template = load_template(template_path)
    template_h, template_w = template.shape[:2]
    if area.shape[0] < template_h or area.shape[1] < template_w:
        return []

    scores = cv2.matchTemplate(area, template, cv2.TM_CCOEFF_NORMED)
    hits = []
    work = scores.copy()
    while True:
        _, max_value, _, max_loc = cv2.minMaxLoc(work)
        if max_value < threshold:
            break
        # 屏蔽邻域，同一个角标只算一次
        half = max(template_w, template_h)
        work[max(0, max_loc[1] - half):max_loc[1] + half,
             max(0, max_loc[0] - half):max_loc[0] + half] = -1.0
        center = (left + max_loc[0] + template_w // 2, top + max_loc[1] + template_h // 2)
        hits.append(center)
    return hits


def _is_at_main_interface():
    """主界面判据复用 common.at_main_interface()。

    只看玩法目录图标会被骗：英雄厅堂等子页的底部栏有同一个图标，实测停在厅堂时
    按 HUD 坐标点赛季手册 / 月桂之旅 / 当前进度三个入口全部落空。
    """
    invalidate_screenshot_cache()
    return at_main_interface()


def _tap_into_panel(pos, name, max_attempts=2):
    """点 HUD 图标进入子面板。

    首次点击可能被窗口激活吞掉，而且这类入口没有可靠的页签锚点（面板会记住上次
    子页，实测月桂之旅的「旅行手记」页签只在赛季月桂之旅II 存在），所以用
    「主界面 HUD 是否消失」判定是否真的进去了，没进去就补点一次。
    """
    def click(corner_pos):
        region = game_client_region()
        click_position(
            (region[0] + corner_pos[0], region[1] + corner_pos[1]), wait=1.8, twice=False
        )

    return tap_hud_entry(
        pos,
        lambda: not _is_at_main_interface(),
        retries=max_attempts,
        click=click,
        log_func=lambda attempt: log(f"第 {attempt} 次点击{name}入口后仍在主界面。"),
        precheck=True,
    )


# 每个手记/行记面板里还有两层页签，实测四本记布局一致（客户区固定 1600x900）：
# 内层「奖励 / 任务」在 y=210，任务下再分「每日 / 每周 / 挑战」在 y=265。
# 文字随记名变（手记任务 / 行记任务），做不了一张通吃模板，故用固定点位 + 切页确认。
JOURNAL_REWARD_TAB_POS = (712, 210)
JOURNAL_TASKS_TAB_POS = (845, 210)
JOURNAL_SUB_TAB_POSS = [(605, 265), (700, 265), (800, 265)]
# 确认「切到任务页」靠子页签那一行：绿色选中胶囊横向移动后自匹配实测掉到 **-0.3**，
# 静止时 1.000。内层页签行本身不能用——真切了页也只有 0.989，而噪声底 0.992（实测），
# 拿它当判据会随机漏扫整片周常/挑战奖励。
JOURNAL_SUB_TAB_REGION = (560, 245, 290, 40)
TAB_SWITCHED_BELOW = 0.97


def _sub_tab_row():
    """取子页签那一行（每日/每周/挑战）的图像，用于确认切页是否真的生效。"""
    win_x, win_y, _w, _h = game_client_region()
    x, y, w, h = JOURNAL_SUB_TAB_REGION
    return get_cached_screenshot()[win_y + y:win_y + y + h, win_x + x:win_x + x + w]


def _row_changed(before, after):
    return crops_differ(before, after, TAB_SWITCHED_BELOW)


def _sweep_journal(name):
    """扫一本手记/行记：奖励页 + 任务页下的 每日/每周/挑战 三个子页签。

    只扫奖励页会整片漏掉任务奖励（每周行记 / 挑战行记 尤其明显）。切页是否真的生效
    由子页签行的自匹配确认，确认不到就不继续——那三个坐标在奖励页上落在奖励列表区，
    盲点等于拿未验证的界面赌。
    """
    win_x, win_y, _w, _h = game_client_region()
    total = _sweep_view(f"{name}-奖励")

    def tap(sub_index):
        sub_x, sub_y = JOURNAL_SUB_TAB_POSS[sub_index]
        click_position((win_x + sub_x, win_y + sub_y), wait=1.0, twice=False)

    click_position((win_x + JOURNAL_TASKS_TAB_POS[0], win_y + JOURNAL_TASKS_TAB_POS[1]),
                   wait=1.2, twice=False)
    tap(0)
    row_daily = _sub_tab_row()
    tap(1)
    if not _row_changed(row_daily, _sub_tab_row()):
        log(f"{name}：没确认切到任务页签，跳过任务子页。")
        return total

    # 确认成功时人已停在「每周」，先把这页扫掉，再依次扫挑战、每日
    total += _sweep_view(f"{name}-任务子页2")
    for sub_index in (2, 0):
        tap(sub_index)
        total += _sweep_view(f"{name}-任务子页{sub_index + 1}")

    # 切回奖励页，让下一本记从已知状态开始
    click_position((win_x + JOURNAL_REWARD_TAB_POS[0], win_y + JOURNAL_REWARD_TAB_POS[1]),
                   wait=1.0, twice=False)
    return total


def _sweep_laurel_journey():
    """主界面右侧「赛季月桂之旅」入口 → 逐个子页签一键领取。

    实测入口图标在客户区 (1550,610)，进去后底部有 4–5 个手记页签（秋夜手记 /
    赛季月桂之旅II / I / 魔法行记），每个页签各自带一键领取，所以逐个切过去扫；
    每本记内部还有 奖励/任务 两层页签，由 _sweep_journal 负责遍历。
    """
    if not _tap_into_panel(LAUREL_HUD_POS, "月桂之旅"):
        log("未能进入赛季月桂之旅界面，跳过。")
        return 0

    win_x, win_y, _w, _h = game_client_region()
    total = _sweep_journal("月桂之旅-当前记")
    for slot_x, slot_y in LAUREL_CAROUSEL_SLOTS:
        check_stop()
        click_position((win_x + slot_x, win_y + slot_y), wait=1.2, twice=False)
        total += _sweep_journal(f"月桂之旅-页签({slot_x},{slot_y})")
    _click_panel_back("月桂之旅")
    return total


def _harvest_idle_chest():
    """赛季挂机关卡页中部的产出宝箱：点开 → 点「收获奖励」。

    实测收获是**静默入账**（没有「获得奖励」弹窗），领完宝箱变成关闭态并重新开始
    计时，所以只能靠模板判断：满箱金光态 1.000 / 空箱关闭态 0.450，收获按钮 1.000 / 0.323。
    """
    chest = find_center_silent(tpl_baoxiang_full, threshold=0.8, timeout=1.5)
    if not chest:
        return False
    click_position(chest, wait=1.2, twice=False)
    if wait_and_click(tpl_shouhuojiangli, "shouhuojiangli", 0.8, timeout=3.0):
        time.sleep(0.8)
        return True
    log("宝箱点开了但没看到「收获奖励」按钮，跳过挂机宝箱。")
    return False


def _sweep_progress_milestones():
    """主界面「当前进度」→ 赛季挂机关卡：挂机收益、产出宝箱、里程碑节点。

    里程碑这页没有一键领取，节点间距实测也不规整（54/65/83 不等，轨道还会随领取平移），
    所以按 54px 栅格逐点试点，只把弹出奖励的算作领取。实测点到未解锁节点与英雄节点
    都不会跳转，因此盲点是安全的。
    """
    if not _tap_into_panel(PROGRESS_HUD_POS, "当前进度"):
        log("未能进入赛季挂机关卡界面，跳过。")
        return 0

    win_x, win_y, _w, _h = game_client_region()

    # 1) 右上角 x440 挂机收益
    idle_claimed = 0
    click_position((win_x + IDLE_REWARD_POS[0], win_y + IDLE_REWARD_POS[1]),
                   wait=1.0, twice=False)
    if _close_reward_popup():
        idle_claimed += 1

    # 2) 中部产出宝箱
    chest_claimed = 1 if _harvest_idle_chest() else 0

    # 3) 里程碑节点栅格
    anchors = _find_all_matches(tpl_milestone_locked, 0.9, MILESTONE_TRACK_REGION)
    row_y = (sorted(anchor[1] for anchor in anchors)[len(anchors) // 2] if anchors
             else win_y + MILESTONE_ROW_Y_FALLBACK)
    node_claimed = 0
    for step in range(MAX_MILESTONE_CLICKS):
        check_stop()
        x = win_x + MILESTONE_X_START + step * MILESTONE_X_STEP
        if x > win_x + MILESTONE_X_END:
            break
        click_position((x, row_y), wait=0.8, twice=False)
        if _close_reward_popup():
            node_claimed += 1

    claimed = idle_claimed + chest_claimed + node_claimed
    log(f"红点领取：赛季挂机关卡 领取 {claimed} 项"
        f"（挂机收益 {idle_claimed}、产出宝箱 {chest_claimed}、里程碑 {node_claimed}）。")
    _click_panel_back("当前进度")
    return claimed


def main():
    """执行红点奖励领取。返回 True=至少进入过其中一个领取界面，False=入口都不在。"""
    log("开始执行红点奖励领取...")
    total = 0
    entered = False

    if _open_task_panel():
        entered = True
        total += _claim_task_panel()
        _click_panel_back("任务面板")
        time.sleep(1.0)
    else:
        log("未能进入任务面板，跳过任务面板领取。")

    check_stop()
    label = find_center_silent(tpl_saijishouchuo, threshold=SEASON_BOOK_THRESHOLD, timeout=1.5)
    if not label:
        # 面板领取可能停在菜单/子页里，HUD 上的赛季手册标签看不到；先回主界面再判一次
        recover_to_main_interface()
        label = find_center_silent(tpl_saijishouchuo, threshold=SEASON_BOOK_THRESHOLD, timeout=1.5)
    if label:
        entered = True
        total += _claim_season_book(label)
    else:
        log("主界面未找到「赛季手册」入口，跳过。")

    check_stop()
    recover_to_main_interface()
    total += _sweep_laurel_journey()

    check_stop()
    recover_to_main_interface()
    total += _sweep_progress_milestones()

    # 收尾必须把游戏带回主界面：中途任一入口失败都可能停在子页面，
    # 交给下一个任务时就会从错误界面开始（实测盲点卡片曾停在「纷战争锋」内）。
    check_stop()
    if not recover_to_main_interface():
        log("领取流程结束时仍未确认回到主界面，请留意下一个任务的起始界面。")

    log(f"红点奖励领取结束，共领取 {total} 项。")
    return entered


if __name__ == "__main__":
    main()
