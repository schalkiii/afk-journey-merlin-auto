# CHANGELOG

## 未发布（Working）

### 远程桌面兼容：后台截图 + 点击前自动激活（`common.py` / GUI）
- **问题现象**：主桌面运行正常，远程桌面（单屏、分辨率不同）运行会点到不该点的地方；迷梦→女神塔等任务衔接时也可能从错误界面开始。
- **根因**：①远程桌面通常只有一个屏幕，机器人窗口盖住游戏，屏幕截图拿到的是机器人界面、坐标点击也落在机器人窗口上；②不同会话/缩放下 DPI 虚拟化会让 `GetClientRect/ClientToScreen` 与物理像素截图错位；③窗口位置在切换分辨率后变化，旧的客户区缓存失效。
- **后台截图**：新增 `windows-capture`（Windows Graphics Capture）可选依赖。WGC 由 DWM 直接合成目标窗口画面，**游戏被其他窗口遮挡时仍能识别**（实测遮挡前后模板命中坐标一致）；不可用时自动回退普通屏幕截图。截图仍是「全屏坐标系」，所有 `find_center` / 点击坐标语义不变。
- **点击前自动激活**：`send_coord` 写入坐标前用 `WindowFromPoint` 判断点击点最上层窗口；被遮挡时把游戏窗口切到前台（含 `AttachThreadInput` 与前台锁兜底），避免点到机器人自己。可通过控制栏「远程桌面兼容（后台截图+自动激活）」整体开关，默认开启。
- **坐标稳定性**：进程启动即声明 Per-Monitor DPI 感知；`game_client_region` 每次调用都重新校验窗口矩形，远程桌面切换分辨率/拖动窗口后不会沿用旧坐标；启动任务时若客户区不是 1600×900 会打印明确警告。
- **构建**：`goldenhandmaidens.spec` 显式加入 `windows_capture` hiddenimport；README 依赖补 `windows-capture`。未安装该依赖时功能仍可用（回退前台截图 + 自动激活）。

### 女神塔 / 迷梦之域衔接修复
- **女神塔「一键碾压」**：部分层数会在「开始挑战」位置显示「一键碾压」按钮，导致找不到 `zhandou` 而中断。新增 `wait_for_battle_start()`，同时轮询 `zhandou` 与可选的 `yijiannianya.png`，命中碾压按钮时点击并继续等待结算/下一层。
  - 该模板需按实际界面补图（当前仓库没有）：未放置 `templates/yijiannianya.png` 时只等待普通战斗按钮，日志会提示一次；模板检查测试已将该文件登记为可选模板。
- **迷梦结算/战绩页清理**：新增 `ensure_back_to_challenge()`，战斗后不仅点「点击空白处关闭」，还会尝试 `exitck` / `exit`，直到重新看到「挑战」按钮；`handle_battle()` 现在把清理结果作为成功条件，避免带着战绩页进入女神塔。

### 推图连续失败上限
- `push.PushFlow` 新增 `max_consecutive_failures`（默认 10，范围 1–99）：失败次数**跨阵容累计**，`end(k)` 成功推进后清零；达到上限时记录 `LAST_STOP_REASON = "fail_limit"` 并退出。配置位于 `push_settings.max_consecutive_failures`，GUI 推图参数面板新增「连续失败上限」输入框，幻灵推图 / 推图 / 循环推图共享；循环推图命中上限时整体停止，不再无限换阵容重试。
- 新增 `tests/test_push_fail_limit.py`：覆盖达到上限转退出、成功推进清零。

### 运行日志与任务状态增强
- 控制栏新增「当前任务」标签（如 `女神塔 (3/12)`），窗口标题同步显示；任务开始/完成/失败日志带 `[序号/总数]` 与耗时（秒）。
- 任务异常时面板记录首行原因，完整堆栈写入 `game_bot.log`，便于远程反馈定位。
- 启动运行前打印截图模式与自动激活状态，并校验游戏客户区尺寸。

### 实测发现并修复
- **狩猎悬赏面板加载竞态**：标题先于卡片/按钮渲染，`_enter_panel` 看到标题就返回，随后 `timeout=0` 的检测直接判空，首次实测出现「搜寻 0 次、加入 0 次」。现在等待搜索/加入按钮就绪（最多 6s），两处按钮检测也改为带短轮询。修复后实测成功搜寻并参加队友悬赏。
- **家园愿望单从公会大厅启动失败**：上一个任务（结社战线/狩猎悬赏）结束时可能停在公会大厅，而大厅底部同样显示「玩法目录」，旧的主界面判定会误认为已在家园，导致找不到左侧「愿望单」入口。`_ensure_panel` 现在找不到入口时先尝试 `fanhui`/`exit`/`exitck` 逐层返回家园再重试。
- **家园愿望单补货链路修正**：实测发现旧实现假设「点途径箭头 → 直接到制作界面」，实际是「自动寻路 → 点角色脚下 F 交互提示 → 生产选择页点『愿望单需求』卡片的『选择』→ 制作界面」；开始按钮也分建筑（厨房「开始烹饪」/锻造「开始锻造」，炼金模板可选）。已新增 `xinyuandanxuqiu.png` / `kaishiduanzao.png` 模板并落地对应流程；数量档、开始按钮、交互提示、选品全部改为单击——`click_position` 默认连点两次会把 x10 多点回 x1。
- **制作原料不足守卫**：点击「开始」后若弹出「当前资源不足」，弹窗会遮住按钮，旧逻辑会把「按钮消失」误判成制作已开始并白等 600 秒。现在弹窗出现即记录「所需原料不足」、关闭弹窗并结束补货。
- **实测记录**：结社战线（进入→挑战→失败结算→扫荡次数为 0→清理回主界面）通过；狩猎悬赏（搜寻至 0/15、参加队友悬赏）通过；家园愿望单（交付 1 单、领奖、寻路、选品）通过。当前账号原料不足以启动 x10 制作（弹窗指向 18 级元素精炼所生产元素精华），因此**完整制作耗时仍未实测**；遇到二级原料不足会安全结束，原 pending 项继续保留。

### 审计遗留项收尾（A3 / A7 / A9 / A10）
- **模板一致性自动检查（A3）**：新增 `tests/test_templates.py`——扫描全项目 `get_template_path("x.png")` 字面量引用，断言每个引用都在 `templates/` 下存在；断言模板尺寸不超过 1600×900 客户区（超了说明是在别处裁的）；未被引用的模板只作信息输出（英雄模板按 ID 动态拼名，静态扫描看不到引用属正常）。
  - 该测试**立即抓到一个既有缺陷**：`warehouse.py` 引用的 `warehouse_title.png` / `warehouse_first_card.png` 在仓库里从未存在过（`git log` 查无此文件）。追查发现唯一使用者 `_locate_first_card()` **从未被任何代码调用**——是遗留死代码（内含「这里的偏移要你根据实际界面调」这类未完成注释）。已删除该函数与两个常量，`CARD_WIDTH` / `CARD_HEIGHT` 仍被其他逻辑使用故保留。
- **GUI 顺序测试产品化（A9）**：`tests/test_gui_order.py`（6 个用例）真实构造 GUI，覆盖重排后脚本/按钮顺序一致、选中项跟随原功能、`script_order` 持久化内容、配置缺新功能时补末尾、单跑目标、以及「位移 <8px 不算拖拽」。整模块共用一个 Tk 根（同一进程反复建根本会随机抛 `TclError`，实测导致用例间歇性 skip），配置文件重定向到临时目录，不污染用户配置。
- **日志轮转（A7）**：`append_log_file` 写入前检查大小，超过 5 MB 就把当前日志改名为 `.1`（只留一份备份）再新建。实测把已增长到 8.86 MB 的 `game_bot.log` 正常滚动，新文件重新开始。`.gitignore` 补上 `game_bot.log.*`，避免轮转出的备份被误提交。
- **补货制作完成等待上限 90s → 600s**：实跑复现了「制作完成等待超时」。查下来不是常量写小一点的问题——早先按 x1 档制作能在 90s 内完成并正常返回，改成「点两下数量档取 x10」后一次生产 10 份，实测 180s 仍不够。上一轮已修的「按钮必须先消失」判据是对的（本次实测确认按钮确实消失、制作真的开始了），问题只在上限。按已知下界把上限提到 600s；**仍未观测到一次完整的 x10 制作返回**，若后续仍超时，说明完成信号不是"按钮重新出现"，需要重新看制作结束后的实际界面。
- **整洁性批量清理（A10）**：删除 8 个文件首行残留的 `# F:\afkj\game-bot\xxx.py` 绝对路径注释；删除 `common.py` 重复的 `_ACTIVE_TEMPLATES_DIR = None`；`random_sleep()` 由 5 个文件各自的副本上移到 `common`（策略变更只需改一处），各文件随之移除未使用的 `import random` 与函数上方的孤儿注释；README 去掉写死的主文件行数、功能表补上公会玩法与家园愿望单两行。

### 架构改进（依据 `doc/AUDIT-REPORT-2026-11-02.md` 的 R1–R5）
- **模板匹配限定到游戏客户区**（R1，实测提速 2.1–3.8x）：`find_center` / `find_center_silent` 在未显式传 `region` 时改用 `common.game_client_region()` 取到的游戏客户区（`GetClientRect` + `ClientToScreen`），返回值仍是全屏绝对坐标、语义不变。桌面 3840×1080 而客户区只有 1600×900，原先每次匹配要多扫约 3 倍像素：单次匹配 216–357ms → 73–106ms，端到端 `find_center_silent` 317ms → 149ms 且**命中坐标完全一致**。未命中时会刷新一次窗口矩形再试，兼容运行中拖动窗口；取不到窗口（非 Windows / 游戏未开）自动退化为整屏，行为与改动前一致。
- **点击器存活探测**（R2）：`click_from_file.exe` 长时间运行后会自行退出，此后所有点击静默落空、表现为「界面连续多轮无变化」——本轮就被它误导过一次诊断。新增 `clicker_alive()`（用当前光标位置作哨兵，避免把鼠标甩到角落）与 `ClickerNotRunning` 异常：`send_coord` 连续 3 次坐标无人消费即报错中止任务，GUI 在每个任务开始前也探测一次、失败则中止后续任务并写明原因。失败方向的取舍：宁可让任务报错（勾选保留、次日重跑），也不让"空转 8 轮后正常结束"把当日任务吞掉。
- **统一任务成败语义**（R3）：`_run_youjian` / `_run_haoyou` / `_run_pujing` / `_run_nvshenta` / `_run_guajijiangli` / `_run_shangcheng` / `_run_meiri` / `_run_pata` 原先全部硬编码 `return True`，其中 5 个流程的 `main()` 根本没有返回值。后果是**失败也会被记为「执行完成」**，而 `daily_reset` 脚本在"成功"后会自动取消勾选——当日任务被静默跳过。现 5 个流程的 `main()` 在任一步骤失败时 `return False`、走完 `return True`，8 个 runner 全部透传。`_run_login` 保持恒真并加注释说明原因（找不到开始界面说明游戏已在登录态，属正常跳过）。
- **统一弹窗关闭路径**（R4）：`dismiss_popup()` 改为复用 `dismiss_popup_away_from()`（点「点击空白处关闭」左上方空白），兜底点从**屏幕底部居中**改成**左下角**——实测底部居中与结社战线「扫荡」、狩猎悬赏「搜寻精怪」、愿望单「交付」重合（偏差仅 2–15px），任务间清理会误触发按钮。
- **配置与模板路径语义统一**（R5）：新增 `common.get_config_path()`（工作目录优先、打包内置回退），`formations.json` / `grid_offsets.json` / `migong_config.json` 改走它——原先走 `get_resource_path`（打包后指向只读的 `_MEIPASS`），用户改 exe 同目录的那份**不生效**。`start.py` 改用 `get_template_path()`，不再自行拼 `templates/` 路径绕过 APPDATA 副本机制。
- **新增测试**：`tests/test_clicker_guard.py`（6 个用例）覆盖点击器漏消费告警、`ClickerNotRunning` 触发阈值、正常消费不误报、客户区限定的坐标换算与区域外不误命中。全部 8 个用例通过。
- **新增 `doc/TEMPLATE-AUTHORING.md`**：把本轮多次事故的根因沉淀成规范——1600×900 采集、避开角标与流光动画、纯色块不可作模板、采完须同时验证"目标界面分 / 最易混淆界面分 / 实点落点"、以及「红点不一定是奖励」（实测可能是剧情对话）。


### GUI：功能列表可拖拽排序 + 支持单独运行一个功能
- **拖拽改执行顺序**：功能列表按钮支持按住上下拖动重排（位移 < 8px 仍视为普通点击，不进入拖拽，避免误改顺序）。关键是消除了「两份顺序数据」——原先执行顺序由 `run_scripts_thread` 里一份硬编码 `script_order` 常量决定，按钮列表只是它的镜像，拖动改了也不生效；现在 `run_scripts_thread` 直接按 `self.scripts` 迭代，列表顺序即执行顺序。重排后按名字找回 `current_script_index`，避免右侧配置面板跳到别的功能上。
- **顺序持久化**：`save_config` 写入 `script_order`（功能名列表），启动时恢复；配置里没有的功能（新版本新增）按默认顺序补到末尾，不会因升级丢顺序也不会漏项。
- **单独运行**：配置面板新增「只运行当前功能」按钮（`run_single_script`），只跑选中的那一个功能并忽略其它勾选，用于逐项验证或补跑漏掉的一天。与「全部运行」共用新的 `_begin_run(scripts, respect_enabled)`，运行态复位 / 状态标记 / 线程拉起只有一份实现。原先 `start_all` 在「没有启用任何脚本」时先置了 `is_running` 再 `stop_all` 回滚，现改为校验不通过直接返回，不再留下一次多余的停止日志。
- 拖拽松手时 ttk `Button` 的 `command` 也会触发，会把「调整顺序」误当成「选中该功能」；用 `_drag_moved` 标志抑制，且该标志延迟到下一次按下才复位（command 与 `<ButtonRelease-1>` 回调的先后顺序不保证）。

### 仓库完整性修复：家园愿望单整个功能此前从未提交
- 核对 `git ls-files` 发现：上一轮只把 `yuanwangdan.py` 和它的 README/CHANGELOG 说明写进了工作区，**代码文件和它依赖的全部模板都没有 `git add`**（`yuanwangdan.py`、`yuanwangdan.png`、`yijianxuanze.png`、`xinyuandanjiaofu.png`、`xinyuandanwancheng.png`、`xinyuandanbuzu.png`、`xinyuandanbiaoti.png`、`tujingjiantou.png`、`kaishipengren.png`、`fanhui.png`、`huodejiangli.png` 均为 untracked）。也就是说 clone 仓库的人既看不到这个任务、跑起来也会 `ValueError: 模板读取失败`。本次连同新增的公会玩法模板一并纳入版本库。
- 教训：新增任务脚本必须和它的 `templates/*.png` 一起 `git add`；只提交 `.py` 等于提交了一个跑不起来的功能。收尾时用 `git ls-files` 对照代码里的 `get_template_path(...)` 清单，比凭记忆可靠。
- `.gitignore` 补齐：`goldenhandmaidens.exe`（打包产物，92MB；`click_from_file.exe` 是运行依赖仍需入库）、`game_bot.log`、`.codebuddy/`、`.workbuddy/`、`_tmp_*`、`_devshots/`。


### 新增每日任务：结社战线 + 狩猎悬赏（`jieshezhanxian.py` / `lieshouxunshang.py` / `flow_gonghui.py`）
- 两个公会日常任务（均 `daily_reset=True`）登记于 `scripts` 列表与 `_run_script_dispatch` 分发表，默认执行顺序排在「异界迷宫」之后、「家园愿望单」之前（顺序现由功能列表拖动决定，见上节）。
- **入口流程单源**：新增 `flow_gonghui.flow_enter_guild_play(card_template, card_name)`，统一「玩法目录 → 公会玩法页签 → 玩法卡片」这段两个任务都要走的跳转。页签有已激活 / 未激活两套外观，单一模板会互相误命中（未激活模板在已激活界面上最高只能匹配到左侧「常规玩法」，实测 0.85），故存 `gonghuiwanfa` / `gonghuiwanfaactive` 两份模板并用 0.95 阈值区分。
- **结社战线**：按「赢了继续挑战、输了才扫荡」实现。实测**挑战不消耗扫荡次数**（打赢一场后「今日剩余」仍为 4），两条计数独立。流程：挑战 → 备战点「战斗」→ 结算出现「继续挑战」即胜利并直接回到下一层备战；否则结束挑战，回主界面点「扫荡」进「扫荡关卡」面板 → 点「最大」档 → 点「扫荡」一次扫完；面板打不开即当日次数已用尽。该玩法**没有**「跳过战斗」入口（整场只能观战），结算等待上限 180 秒；单次任务最多挑战 20 场。
- **狩猎悬赏**：玩法目录里的卡片**只做传送**（把角色传进公会大厅），还需再点大厅里的「狩猎悬赏」招牌才进面板。面板内①循环点「搜寻精怪」用掉自己的次数（次数耗尽时按钮变灰底深字，实测灰态最高只匹配到 0.53，故「按钮还匹配得到」本身就是「还有次数」的判据，无需读数字）；②在卡片网格内循环点「加入」参加队友悬赏（每日 3 次）。悬赏奖励自动结算，「我的记录」里的奖励图标只读（实测点击无响应），故不做领奖步骤。
- **「点击空白处关闭」热区陷阱**（新增 `common.dismiss_popup_away_from`）：该提示文字固定在屏幕底部居中，而结社战线「扫荡」按钮与狩猎悬赏「搜寻精怪」按钮正好压在其下方 2–15 像素内——在热区中心关闭结算会**同时再触发一次该按钮**（实测关掉「扫荡完成」后立刻又扫一次、关掉「发现悬赏目标」后立刻又抽一次）。改点该文字左上方 (-400, -200) 的空白处，同样能关闭且不误触。
- **点击原语下沉**：新增 `common.click_position(pos, wait, twice)`，统一「匹配到的全屏坐标 + 前台补偿连点」；跳转类按钮传 `twice=False`（连点会「进入后又退出」）。
- **胜利/失败结算区分**：胜利结算的「继续挑战」与失败结算的「再次挑战」只差首字、按钮样式相同（实测互相能匹配到 0.782），故「继续挑战」用 0.85 阈值并同时轮询失败标题 `jiesheshibai`——认出失败立刻结束挑战，不必等 180 秒超时。
- **「加入」模板只裁两个字**：按钮上的数字是自己剩余参加次数（加入3/3 → 加入2/3），含数字的模板在次数变化后就匹配不到；又因该模板很小（48×26），限定在由面板标题中心推算的网格区域内匹配。加入成功后列表会重排、同一位置可能换成另一张仍可加入的卡片，故不能用「原位置是否还匹配得到」判断本次点击是否生效（实测把真实成功误判成被吞掉、少计一次），改为按点击计数并由上限收敛。
- 新增模板 18 个（1600×900 客户区采集）：`gonghuiwanfa` / `gonghuiwanfaactive` / `jieshezhanxian` / `jieshezhanxianbiaoti` / `jieshetiaozhan` / `jieshesaodang` / `jieshesaodangguanqia` / `jieshesaodangmax` / `jieshesaodangbtn` / `jieshengli` / `jiesheshibai` / `jieshejixutiaozhan` / `jieshesaodangwancheng` / `lieshouxunshang` / `lieshouxunshangbiaoti` / `lieshouxunshangdating` / `lieshoujingguai` / `lieshoujiaru`。复用既有 `wanfamulu` / `exit` / `zhandou` / `dianjikongbaichuguanbi` / `libao` / `tuichulibao`。
- 从结社战线退出必弹「专属装备礼包」广告，两个流程收尾都调 `jiance.check_and_handle_libao()` 清理。
- README 补充「11. 公会玩法日常」与项目结构条目。

### 家园愿望单修复：模板按 1600×900 重采 + 偏移量重标定
- **根因**：愿望单那批模板是在 **1302×1080** 窗口下采集的（旧调试截图 `_tmp_*.png` 均为 1302 宽，`yijianxuanze` 在其上仍匹配 0.934 可反证），而项目文档与其余模板都按 1600×900。游戏 UI 不随窗口等比缩放（1302×1080 与 1600×900 宽高比差异大），所以整套模板与按像素标定的偏移量在当前分辨率下全部失效——实测入口 `yuanwangdan` 0.590、`yijianxuanze` 0.487，任务表现为「已点击愿望单入口 → 未进入愿望单界面，任务终止」。
- 重采 6 张模板：`yuanwangdan`（入口，改为只裁礼盒主体 48×48，避开左上角紫色档位角标与右上完成角标——旧图把角标和背景一起裁进去，角标消失或家园季节底色变化即失配）、`yijianxuanze`、`xinyuandanjiaofu`、`xinyuandanbiaoti`、`huodejiangli`、`xinyuandanwancheng`。
- **结算判定加兜底**：「完成愿望单」标题带流光动画，实测同一模板连续帧匹配分在 0.82–0.95 抖动，0.8 阈值随时会漏判。曾尝试改用标题下方静态的虚线 + 「基础奖励」标签条（连续帧 min 0.998），但该图案太通用、在家园视图左上角也能匹配到 0.858，反而把状态机永久卡在 result 空转——已回退。现改为：标题仍作主判据，并在 `_panel_state` 末尾加「有『点击空白处关闭』提示且其余四态都排除」的兜底分支；判定顺序同时调整为 领奖 > 不足 > 交付 > 一键选择 > 结算（弹窗压住面板时面板按钮只会匹配到 0.43–0.50，不会与结算抢判）。主循环里原先「认不出界面就点空白关闭」的分支因已被兜底覆盖而成为死代码，一并移除。
- **去掉两处像素魔数**：结算 / 领奖弹窗的关闭点原按「标题中心 + (67,711) / (7,697)」推算，随分辨率变化即失效；新增 `_close_by_blank_hint()` 直接用 `dianjikongbaichuguanbi` 模板定位（该提示在底部居中，而面板主按钮在其上方 60 余像素，不会像结社战线「扫荡」那样与热区重合）。礼盒可点击点 `GIFT_CLICK_OFFSET` 按 1600×900 重标定为 (120, 40)。
- **进度奖励改为按需试领**：原先每轮都点一次礼盒、并用 `claim_attempts < MAX_CLAIMS` 限「尝试次数」——礼盒常亮但无可领档位时每轮白点一次（每次约 3 秒），且 10 次尝试额度会在任务前期就耗光，导致后面真解锁的档位再也领不到。改为只在「进度可能刚变」时试（开局 + 每次交付后），额度语义也从尝试次数改为成功次数。
- `_click` / `_click_once` 改为 `common.click_position` 的薄包装，消除与新增两任务间的重复实现。
- **补货（资源不足→自动制作）分支已跑通**：实测连续 3 轮「缺料 → 自动寻路 → 进厨房 → 切档 → 制作 → 回愿望单 → 继续交付」全部成功（本次跑到第 6 单交付）。关键修正两处：
  - `kaishipengren.png` **原先裁错了位置**——裁到锅按钮右侧的飘带背景（客户区 x 948..1063 / y 826..852），所以「开始烹饪」的点击一直落在无控件处。按 1600×900 网格重量为锅+标签整块（x 745..860 / y 735..850，中心屏幕 2896,859），新模板在厨房匹配 1.000、在其他界面 ≤0.44。
  - 数量档不再用 `zhizuox10` 模板反查：进建筑时档位固定是 x1，而档位是 x1 → x5 → x10 循环，反查失败会继续点、可能从 x10 又绕回 x1（越确认越偏）。改为固定点两下取 x10（`QTY_CLICK_TIMES = 2`），并移除 `tpl_x10` 引用。`QTY_BUTTON_OFFSET` 重标定为 (110, -10)。
- **「一键选择」改用单击**（本次实测的关键修复）：缺料时点「一键选择」会弹出「当前资源不足」弹框，而 `_click` 的连点补偿第二下正好落在该弹框上把它关掉——状态机因此永远只看到 `one_key`，既进不了补货分支也判不出「这单做不了」，最后白耗 8 轮空转退出（`交付 0 单`）。改单击后整条链路打通。
- **新增 `_wait_gone()` 防假成功**：原实现点完「开始烹饪」只 `sleep(2)` 就等按钮「重新出现」，点击未生效时按钮根本没消失，会被立刻判成「制作完成」并白跑一轮。现改为先确认按钮真的消失（这批确实开始）再等它重新出现。
- **本轮踩到的两个诊断陷阱**（写下来避免下次再据此下错结论）：
  - `click_from_file.exe` 会在长时间运行后自行退出，退出后坐标文件仍被写入但无人消费，**所有点击静默落空**。中途一度把「厨房按钮点不动」误判成界面逻辑变了，实际是点击器已死。判据：写一条坐标后轮询文件是否消失；同时 `tasklist` 确认进程存活。
  - 校验「点击是否生效」不能用 `wanfamulu`：主界面和玩法目录面板的底部导航里都有它，匹配得到 ≠ 没跳转（实测据此得出完全相反的结论）。要用只在目标界面出现的模板。
- 另 `templates/xinyuandanjiangli.png` 无任何代码引用（上一版遗留），未纳入版本库。

### 新增每日任务：家园愿望单（`yuanwangdan.py`）
- 新任务「家园愿望单」（`daily_reset=True`，成功后自动取消勾选），登记于 `scripts` 列表、`_run_script_dispatch` 分发表与 `script_order` 执行顺序。**执行顺序置于末尾**：该任务在家园视图内执行，结束后游戏停留在家园，而项目其余流程以主界面「玩法目录」(`wanfamulu`) 为起点判定，排在中部会阻断后续所有任务。
- 完整闭环：左侧「愿望单」入口 → 循环「一键选择」→「交付」→ 关闭「完成愿望单」结算，逐单交付；库存不足时弹「当前资源不足，可从以下途径获取」，点击途径箭头自动寻路到生产建筑，切 x10 档位后「开始烹饪」制作 10 份，再逐层返回家园继续交付。
- 四态互斥判定（结算 > 不足弹框 > 已选待交付 > 待选择），全部模板匹配，无 OCR 依赖。
- **进度奖励自动领取**：左上角「愿望单」进度条满后，礼盒图标带橙色角标即可领取。礼盒图标在不同档位下外观不同（第一档金色心形、第二档青色宝石），模板匹配无法跨档位，故改用「愿望单」标题标签(`xinyuandanbiaoti.png`)做锚点、按偏移 (80, 45) 点击其右侧礼盒区域（实测有效点）。已领取状态下点击无副作用，故每轮安全尝试，以弹出「获得奖励」(`huodejiangli.png`) 为准；弹窗关闭热区按标题偏移 (7, 697) 定位。单次任务最多领 10 次。
- **前台点击补偿**：游戏未处于前台时，第一次鼠标事件会被系统用于激活窗口而被吞掉，故每次点击连点两次（间隔 0.25 秒）；窗口已激活时两次点击等价，本流程的点击目标均为幂等操作，重复点击无副作用。该补偿逻辑已上移为 `common.click_position(pos, wait, twice)`，`yuanwangdan._click/_click_once` 改为薄包装，结社战线 / 狩猎悬赏 共用同一份。
  - 勘误：本条早期版本写作「`click_from_file.exe` 改用 SendInput 原子点击」，但仓库内 `click_from_file.exe` 与 `HEAD` 中的 blob 字节一致（自 v1.4.3 未变），exe 里并没有该改动。真实的 SendInput 原子点击实现落在上一轮遗留的临时提权点击服务脚本里（协议与 AHK 一致：轮询 `shared/target_coord.txt`、读走即删），它替代的是「长时间无人值守下会自行退出、导致点击全部落空」的 exe，而非被编进 exe。该脚本自带「验证后删除」注释，但记录了两个必须留下的事实：① 游戏以管理员权限运行，未提权进程的注入会被 UIPI 丢弃（实测坐标文件被正常消费而游戏毫无反应）；② `mouse_event` 分离调用 LEFTDOWN/LEFTUP，进程在两者之间被中断会让左键永久卡住（曾导致用户所有窗口被最小化），故必须用 SendInput 一次提交。据此保留该脚本不删，并在 README 记录提权要求。
- 每日档位实测：5 → 40 → …（领取后目标值提升）。
- **关键行为修正**：「一键选择」只填入需求并把按钮变橙色「交付」，必须再点一次才真正提交——只点一次会停在已选择状态空转（首版按「一次点击即完成」实现，实测卡在 0/3）。
- 所有点击坐标由模板匹配获得（`find_center_silent` 返回全屏坐标）：结算关闭热区按标题偏移 (67, 711) 推算，返回箭头由 `fanhui.png` 定位；**不使用硬编码窗口坐标**（首版硬编码窗口内坐标导致点击落到屏幕其他位置、结算界面卡死 22 分钟）。
- 生产界面有两层（制作界面 → 产品选择列表 → 家园），返回需连点两次箭头，故按「愿望单入口可见」为终止条件最多连点 3 次。
- 数量档位为 x1 → x5 → x10 循环（进建筑默认 x1），以「最大档」模板判定是否已切到 x10，最多点 3 次；制作中「开始烹饪」被进度指示替换，以其「消失→重现」作为完成信号。
- 安全阀：单次任务最多交付 20 单、最多制作 5 次、同一状态连续 8 轮无变化即判定卡死退出。
- 新增模板：`yuanwangdan.png`（入口，66×65，已裁掉右上角未完成角标）、`yijianxuanze.png`（一键选择，381×51）、`xinyuandanjiaofu.png`（交付，420×58）、`xinyuandanwancheng.png`（完成结算标题，320×90）、`xinyuandanbuzu.png`（资源不足标题，300×34）、`tujingjiantou.png`（途径箭头，52×50）、`kaishipengren.png`（开始烹饪，180×95）、`zhizuox10.png`（x10 档位，76×46）、`fanhui.png`（返回箭头，67×53）。
- README 补充「10. 家园愿望单自动交付」与项目结构条目。

### 合并上游 v1.4.7（yangyh02/afk-journey-merlin-auto @ 6c7bbb8）
- `push.py`：礼包遮挡检测改为「连续 3 轮未命中候选模板」才触发（避免单轮误判）；`_st_on_end` 成功推进后重置 `lineup_start=0`（下一轮从第一套阵容开始）；新增 `_click_next_lineup`（连续 3 次短等待识别 right，全部失败才判定阵容用完）。
- `Goldenhandmaidens.py`：新增**本地持久化日志文件** `game_bot.log`（早期 `_PersistentStdout` + 运行期 `_StdoutTee` 双写文件 + `log()` 写文件；日志窗口新增「刷新 / 清空文件」按钮；文件写入失败时弹窗提示移到可写目录）；**循环推图**失败/异常由 `break` 改为 `continue`（与上游一致，单模式结束/失败不视为循环失败），并保留本仓「30 秒快速轮次」防空转安全阀（连续 3 轮 <30s 才停止）。
- `hero_metadata.py` / `warehouse.py`：新增英雄 `aidejia` / `sainie` / `xing` 元数据与种族/职业/中文名。
- `templates/`：新增 `aidejia.png` / `aidejia2.png` / `sainie.png` / `xing.png` 四张模板。
- `version.py`：升至 `v1.4.7`。
- 冲突解决：上游 v1.4.7 把本仓已拆到 `bot_runtime.py` 的顶层函数（`get_work_path` / `CONFIG_FILE` / `load_config` 等）连同新增日志设施整段加回 `Goldenhandmaidens.py`；本仓保留 `bot_runtime` 拆分，并将新增的日志设施（`LOG_FILE` / `_PersistentStdout` / `append_log_file` / 文件写入失败回调）落地到 `bot_runtime.py`，避免重复替换 `sys.stdout` 造成 stdout 接管冲突。

### 文档同步（neat-freak 收尾）
- README「日志机制」描述修正：`_panel_log` 已不存在，改为 `_StdoutTee`（`bot_runtime`）+ 队列 `_enqueue_log` / `_drain_log_queue` 调度到主线程写面板，并经 `append_log_file` 持久化到 `game_bot.log`；`log()` 同样写面板并落盘。
- README「循环推图」行为修正：v1.4.7 合并后单个模式失败 / 异常**不停止**（自动切换到另一模式继续下一轮），仅连续 3 轮在 30 秒内异常结束或 F9 才停止——与代码一致。
- README「巨型主文件拆分」行数声明同步为「约 1568 行」（合并 v1.4.7 后 `Goldenhandmaidens.py` 由约 1483 行增至约 1568 行）。

### 代码审查优化（全面 review）
- `common.find_center_silent` 改用 `get_cached_screenshot()`：与 `find_center` 一致复用短 TTL 截图缓存，
  使 `recover_to_main_interface` / `dismiss_popup` / `ensure_main_interface` 及 7+ 个 flow 脚本的紧循环
  每次恢复迭代从 5 次截屏降到 1 次。
- `push.py` 本地 `find_center_silent`（覆盖 common 同名函数）同样改用缓存截图，消除重复截屏。
- `common.PRINT_MATCH_SCORE` 默认 `True` → `False`：原每帧匹配都打印一行分数，高频轮询下淹没真实日志并徒增
  队列压力；保留为可一键开启的调试开关。
- `common.wait_and_click` 删除从未被调用方使用的 `cooldown` 参数（死代码）。
- `drag_utils.wait_for_drag_complete` 循环内增加 `check_stop()`，使拖拽等待可被 F9 立即中断
  （原仅受 timeout 限制，最长阻塞 10s）。
- `jiance.check_and_handle_libao` 修复双重 `time.sleep`：检测命中分支会连续睡眠两次（约 1.0s/周期），
  移除多余一次，恢复为单次 `interval`。
- 审查确认：`StopRequested` 继承自 `BaseException`，且全仓无 `except:` / `except BaseException` 裸捕获，
  停止信号可正确穿透；`_StdoutTee` 始终以 `sys.__stdout__` 为原始输出，多次运行不会叠加 tee 导致日志重复。

### 隐藏启动/关闭时的黑色控制台窗口
- 根因：PyInstaller 控制台模式会为 `print()` 分配一个 Windows 控制台窗口（启动/关闭时闪现）。
  `goldenhandmaidens.spec` 本就是 `console=False`（窗口模式），但原 `sys.stdout` 重定向仅在点击「开始」后的
  `run_scripts_thread` 内设置，窗口模式下启动期 `sys.stdout` 为 `None`，存在早期 `print` 写入 `None` 崩溃隐患。
- 修复：将 stdout 重定向提前到 `main()` 启动最早期（`sys.stdout = _StdoutTee(...)`）；启动前的 `print` 先缓冲到
  `_early_stdout_buffer`，GUI 实例创建后切换到面板 sink（`_enqueue_log`）并补刷缓冲；退出时由 `sys.__stdout__`
  改为重置为 `_StdoutTee(self._enqueue_log)`，避免窗口模式下重置为 `None` 致后续 `print` 崩溃。`_StdoutTee` 对原始
  输出失败已做 try/except 吞掉，窗口模式安全。
- 重新打包：`pyinstaller goldenhandmaidens.spec --distpath . --workpath build --noconfirm`，引导器自动选用
  `runw.exe` 窗口版，根目录 `goldenhandmaidens.exe` 已更新为无控制台版本。日志仍经 `_StdoutTee` 显示在应用内
  「运行日志」面板；`click_from_file.exe` 早已用 `CREATE_NO_WINDOW` 隐藏，不会闪黑框。

### 代码审查后续：落实 3 项建议
- **统一 `find_center_silent`**：`common.find_center_silent` 合并 `push.py` 之前自带的轮询副本，新增
  `timeout` / `interval` 参数（默认 `timeout=0` 单帧检测，向后兼容其余 7+ 个 flow 脚本的 `region` 调用），
  循环内调用 `check_stop()`。`push.py` 删除本地重复实现，改为薄包装 `find_center_silent(..., timeout=3.0)`
  保留原「最多轮询 3s」语义。消除两份逻辑分叉。
- **`run_scripts_thread` 巨型 if/elif 改为字典分发**：抽出 15 个 `_run_*` 方法与 `_run_script_dispatch`
  分发器，按脚本名查表调用；导入失败由分发器统一捕获返回 False。逻辑与重构前一致（成功→完成、
  导入失败→失败、运行期异常→错误、未实现→失败）。约 190 行分支缩减为查表，更易维护。
- **`send_coord` 等待循环增加 `check_stop()`**：AHK 迟迟未消费上一条坐标时，原本最长阻塞 1s 且无法中断，
  现允许 F9 在等待期间立即中断。

### 代码质量机械整改（ruff 0.16.2）
- 死代码 / 未用导入：移除 22 处未用 import、2 处无占位符 f-string（改普通字符串）、
  `nvshenta.py` 两处死导入 `import os`、`warehouse.py` 死变量 `knight_card_height`、
  `Goldenhandmaidens.py` 重复 `import contextlib`、`warehouse.py` 冗余 `typing.Optional`。
- 简化 / 现代语法：9 处 `open(f, "r")` → `open(f)`；`Optional[X]` → `X | None`（PEP604）；
  11 处未用循环变量改名 `_x/_y/_w/_h`；6 处 try/except/pass → `contextlib.suppress`；
  3 处 if-else 块改三元；2 处 `return True if c else False` → `return c`；`zip(..., strict=True)`；
  `endswith` 合并为元组；去掉 `int(round(...))` 冗余 int。
- 真实隐患修复：`flow_migong.py` `handle_failure(lambda: challenges - 1)` 改为
  `lambda challenges=challenges: challenges - 1`，避免 lambda 延迟绑定循环变量（B023）。
- 验证：ruff F/B/SIM/UP/C4/PIE810/RUF046 全绿；25 个顶层模块导入冒烟测试通过。

### 隐藏启动/关闭时的黑色控制台窗口
- 根因：PyInstaller 控制台模式为 `print()` 分配 Windows 控制台。`goldenhandmaidens.spec` 本就是
  `console=False`，但原 `sys.stdout` 重定向仅在点击「开始」后设置，窗口模式启动期 `sys.stdout=None` 有崩溃隐患。
- 修复（`Goldenhandmaidens.py`）：`main()` 首行即接管 stdout（`_StdoutTee`），启动前 print 缓冲、GUI 建好后
  灌入面板；退出重置改为 `_StdoutTee(self._enqueue_log)`。
- 重新打包引导器选 `runw.exe` 窗口版，根 `goldenhandmaidens.exe` 已更新为无控制台；日志仍进「运行日志」面板，
  `click_from_file.exe` 早已 `CREATE_NO_WINDOW` 隐藏。

### 架构去重与工程化（本轮）
- 英雄识别去重：抽出 `warehouse._match_best_hero(face_roi, scale_min, scale_max, scale_step)`，统一三处
  `_recognize_hero` / `_best_multiscale_match_score` / `_iter_scales`（仓库扫描用 `HERO_TEMPLATE_SCALE_*`、
  阵容识别用 `LINEUP_HERO_TEMPLATE_SCALE_*`），匹配算法单源、行为完全不变，消除仓库扫描与阵容识别分叉隐患。
- 截屏缓存下沉：缓存逻辑内置进 `screenshot_bgr`（短 TTL 0.05s，每次仍 `check_stop` 保证 F9 即时中断），
  `wait_and_click` 点击后 `invalidate_screenshot_cache()` 使下一帧为最新；长任务重复截屏开销降低。
- `goldenhandmaidens.spec` 的 `hiddenimports` 改为 `glob` 自动收集顶层模块，新增 flow 脚本无需手改。
- 测试基线：新增 `tests/test_smoke.py`（pytest），覆盖全模块导入 + `_is_lineup_acceptable` 判定（2 passed）。
- 修复 `flow_migong` lambda 延迟绑定循环变量隐患（B023）。

### 工程化（第二批）
- 点击辅助统一到 `common`：`click_and_wait`（冷却双检跳转）与通用 `click_template` 抽到 `common`；
  `flow_migong.click_mg` 保留为薄包装（migong 模板命名 / `cfg` 阈值解析后调 `common.click_template`），消除各脚本重复包装 `wait_and_click`。
- 阵容可采纳判定去重：`push` / `flow_tower` 两份相同 `_is_lineup_acceptable` 收敛为 `common.is_lineup_acceptable`
  （参数化 `level_score` / `special_hero_set`），两模块保留 1 行包装注入各自常量（push 含 `meimo`、flow_tower 为空），行为不变。
- 巨型主文件拆分：`Goldenhandmaidens.py` 顶层独立工具（stdout 接管 / 配置 / `ScriptConfig` / 快捷方式 / 窗口聚焦）抽到 `bot_runtime.py`，
  主文件由约 1637 行降至约 1443 行；原引用经 `from bot_runtime import (...)` 不变，无行为变化；`bot_runtime` 由 spec `glob` 自动收集。
- 坐标 IPC 维持文件通道（不做内存级改造）：AHK 端 `click_from_file.exe` 为编译产物、无 `.ahk` 源码，`send_coord` 写 `shared\target_coord.txt`、AHK 读取点击不变；
  尾部无条件 `time.sleep(0.5)` 改为「写后等 AHK 读走（文件被删除）再返回」，命中即返回更快且保证点击已发生，AHK 未运行退化为 0.5s 超时，行为不变。
- 验证：pytest 2 passed（全模块导入 + `_is_lineup_acceptable` 判定）；ruff F/B/SIM/UP/C4 全绿；`goldenhandmaidens.exe` 用 `runw.exe` 窗口引导器重建。

### 功能面板：一键全不选
- 配置面板「开启」勾选框旁在「一键全选」基础上并排新增「一键全不选」按钮，调用 `GameBotGUI.disable_all_scripts()`：
  一键将所有功能脚本 `enabled` 置 False（仅改启用状态，不影响各脚本 `daily_reset` 每日重置标记），刷新当前面板勾选框与列表 `✓` 标记并持久化到配置。

### 文档同步（neat-freak 收尾）
- README「项目结构」补齐实际模块：`push.py`（主线推图流程，原缺失）、`bot_runtime.py`（主文件拆分抽出的独立工具，原缺失）、`pata.py`（爬塔入口，被「爬塔」任务分发且内部调用 `flow_tower`，原缺失）；`flow_push.py` 标注由「推图流程」修正为「幻灵推图流程（薄封装）」，`flow_tower.py` 修正为「爬塔内部流程模块（被 pata.py 调用）」，与运行分发（`_run_pata`→`pata.main()`→`flow_tower.flow_tower()`）一致。
- README「项目结构」进一步补齐其余任务脚本（`youjian.py` 邮件、`pujing.py` 普竞、`nvshenta.py` 女神塔、`shouquguajijiangli.py` 挂机奖励、`shangcheng.py` 商城、`meirirenwulingqu.py` 日常任务）与工具（`youyishangcheng.py` 友谊商城、被商城调用；`jiance.py` 礼包/弹窗检测、被多任务复用），现已覆盖全部根目录任务 / 流程脚本。
- README「快速开始」补充推图 / 幻灵推图 / 循环推图 三者关系（源自 `run_scripts_thread` 运行分发代码）。
- README「巨型主文件拆分」行数声明同步为「约 1443 行（经后续增强，当前约 1483 行）」，与 `Goldenhandmaidens.py` 现状一致。

### 合并上游 v1.4.6（merge e4adc3d）
- **push.py 重构为显式状态机**（上游）：11 个状态 + `MAX_LINEUP_SCAN=30` / `MAX_TRANSITIONS=500` 安全阀，
  礼包遮挡自动恢复（tuichulibao）、战斗监控 5s 无 zidongtiaozhanzhong 触发 huidaoguaji 兜底、180s 无法判定按失败结束；
  `flow_push_mode1` / `main` 返回 True/False。`SPECIAL_HERO_SET` 新增 `kululu`、`shizi`（拥有即可，不看练度）。
- **模板缓存健壮性**（上游）：`_templates_marker` 升级 sha256 内容摘要；APPDATA 缓存改为 staging 旁路复制 → 校验 →
  原子替换，残缺缓存不再被误用；新增 `load_template()`（读取失败自动修复缓存并重定位），`find_center` /
  `find_center_silent` 与 warehouse / flow_tower / flow_migong 的模板读取统一走 `load_template`。
- **循环推图防空转**（上游）：每轮记录耗时，连续 3 轮 <30s 异常结束自动停止；幻灵推图 / 推图返回 False 或抛异常
  也立即停止；「推图」任务直接采用 `push.main` 返回值作为成败。
- **本仓修正上游回归**：上游 `PushFlow.run()` 恒返回 False（`_done(True)` 从未被调用），会把「阵容用尽正常跑完」
  误判为失败、令循环推图一轮即停——本仓将 `_st_exit`（唯一正常完成出口）改为返回 True，其余失败 / 安全阀仍为 False。
- **合并策略**：push.py 以上游状态机为基底回植本仓三处去重（`find_center_silent`→common 且调用点显式
  `timeout=3.0` 保留原轮询语义；`_recognize_hero`→`warehouse._match_best_hero`；`_is_lineup_acceptable`→common 注入常量），
  删除上游新流程已无调用的 `wait_for_appearance` / `wait_for_any` / `_try_detect_and_click_entry` 死代码；
  保留本仓增强版 `flow_enter.py` 与 `CLAUDE.md`（上游删除，本仓仍作 AI 规则文件）；version → v1.4.6；exe 已重建。
- 验证：py_compile 全过、pytest 2 passed、ruff F/B/SIM/UP/C4 全绿。

## 重新打包 exe 与清理冗余
- 用 PyInstaller 6.22.0 + `goldenhandmaidens.spec` 重新打包，根目录 `goldenhandmaidens.exe` 已更新
  （含本轮全部源码改动：日志队列节流、`find_center_silent` 统一、任务字典分发、停止检查加固等）。
- 删除游离测试脚本 `test_hero_match.py`（未被任何模块引用）。
- 打包生成的 `build/`、`dist/` 临时构建目录已清理，仅保留根目录新 exe。

### 新增：卡死自动兜底回主界面（防连锁卡死）
- `common.recover_to_main_interface()`：任务卡在某界面（弹窗 / 子界面）反复检测不到目标时，依次尝试点击
  「点击空白处关闭」(`dianjikongbaichuguanbi`) / `tuichulibao` / `exitck` / `exit` 逐层退出，直到主界面
  `wanfamulu` 可见；无任何退出按钮时点击屏幕空白处兜底。
- `common.ensure_main_interface()`：任务切换前先关闭残留弹窗并确保回到主界面，避免上一任务卡在子界面
  导致后续任务 `wanfamulu` 检测失败、连锁卡死。
- `common.wait_and_click()` 新增 `recover_threshold` 参数：某目标连续检测失败达到该次数即触发一次兜底回主界面、
  从卡住处退出后继续等待目标（默认 0 关闭，单次调用最多 `max_recoveries=2` 次）。
- 各任务入口的 `wanfamulu` 检测启用 `recover_threshold=20`；运行循环每个任务开始前（除「登录」外）调用
  `ensure_main_interface()`。
- `flow_enter.flow_return_main()` 改为复用 `recover_to_main_interface()`，统一包含 `tuichulibao` / `exitck` 退出按钮。

### 修复：Lint（basedpyright 严格模式噪音）
- 新增 `pyrightconfig.json`，将 `typeCheckingMode` 设为 `basic`，消除项目（无类型标注的 tkinter 代码）
  中 `reportUninitializedInstanceVariable` / `reportUnknown*` / `reportUnannotatedClassAttribute` 等
  风格级噪音（原 Goldenhandmaidens.py 有 46 error + 645 warning）。
- 修复 `Goldenhandmaidens.py` 中 6 处真实可选类型报错：`_StdoutTee._orig` 的 `None` 成员访问、
  `ScriptConfig.last_run_time` 标注为 `str | None`、`show_log_window` 与 `_schedule_loop` 增加对
  `log_text` / `scheduled_time` 为 `None` 的守卫。修复后该文件 0 诊断。
