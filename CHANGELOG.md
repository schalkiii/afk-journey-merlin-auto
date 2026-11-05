# CHANGELOG

## 未发布（Working）

本段索引（按主题分组；正文条目逐字保留，仅调整小节归类与顺序）：
- **新功能与入口补全**：魔法行记/月桂之旅内层页签、好友与「目标」入口、翻翻乐、英雄厅堂快速升级、红点领取补全与红点奖励领取、推图连续失败上限、结社战线/狩猎悬赏、家园愿望单。
- **判据与流程修正**：主界面判据、实测中修掉的四个既有坑、女神塔/迷梦衔接、实测发现并修复、愿望单模板重采、卡死自动兜底回主界面。
- **实机勘察结论**：活动页与其余入口勘察（惊秋之夜、纷战争锋、钓鱼、神秘屋等）。
- **日志、GUI 与工程化**：日志格式统一、子脚本日志落盘、GUI 勾选/状态色/拖拽排序、远程桌面兼容、运行日志增强、隐藏控制台、一键全不选、重新打包。
- **测试、依赖与代码质量**：纯逻辑测试 B3、依赖清单 B1、审计遗留项收尾、仓库完整性、代码审查与 ruff 整改、架构改进 R1–R5、架构去重、Lint。
- **上游合并与文档同步**：合并 v1.4.7 / v1.4.6、两轮 neat-freak 文档同步。
- **审计改进第二批**：区域变化原语与 HUD 入口 helper、日志出口统一、多实例检测向量化、构建入口与 lint 基线、整洁性收尾。

### 新功能与入口补全

#### 魔法行记 / 月桂之旅：内层「任务」页签从没被切过（本轮测试发现的真漏领）
- **测试结论**：`英雄厅堂` 自动快速升级实测连点 **10 级全部成功**（每次升级后按钮会短暂消失，靠 `wait_and_click` 重试兜住，日志表现为「第 1 次未找到 → 第 2 次识别成功」）；`魔法行记` 入口与轮播点位都对（点 (880,845) 标题确实变成「魔法行记」、底部高亮跟着），当天 70/71 级奖励已领、72+ 未达，所以 0 项是**正确结果**。
- **但发现整片漏领**：每本记内层还有「奖励 / 任务」两页签，任务下又分「每日 / 每周 / 挑战」三个子页签——旧 `_sweep_laurel_journey` 只切轮播、从不切内层，**每周与挑战奖励永远扫不到**。
- **判据差点做错**：先用「内层页签行切页前后自匹配」确认，实测**静止噪声底 0.992、真切了页只有 0.989**——信号比噪声还小，这个判据会随机漏扫。改用「子页签那一行」：静止 **1.000**、切页掉到 **-0.3**（绿色选中胶囊横向移动，`TM_CCOEFF_NORMED` 直接负相关），余量三个数量级。
- 新 `_sweep_journal`：扫奖励页 → 切任务页 → 用子页签行**自证切页成功**才继续扫 每日/每周/挑战，确认不到就停（那三个坐标在奖励页落在奖励列表区，盲点是拿未验证的界面赌）；扫完切回奖励页，让下一本记从已知状态开始。
- 实机验证：单本记四页全扫到、完整 `_sweep_laurel_journey` 五本记跑通且无「没确认切页」告警、收尾回主界面成功。
- 测试：`tests/test_hongbaolingqu.py` 加 2 条（确认成功必须扫满 4 页并切回奖励页；确认失败只许点 3 下就停）。

#### 好友与「目标」两个角落入口补全（用户指出这两处还有可领）
- **实测领到 3 项**：好友「一键赠礼并收取」（收礼进度 2/10 → **10/10**）+ 每日任务页签 1 项 + 公会任务页签 1 项。
- **好友：收礼进度宝箱是自动入账，不需要单独点**。进度满 10 的瞬间当场弹「获得奖励」、宝箱变打勾态——所以脚本**不去点宝箱**，避免把打勾宝箱当可领。另实测「一键赠礼并收取」点**一次**当天就赠完并收完（按钮随即变灰）；仍改成**点到按钮消失为止（上限 3 次）**，防它分「发送 / 收取」两段时一次点不完。
- **好友面板另两个页签无可领**：公会成员是成员列表、家园借用显示「暂无可临时借用建筑的家园」+ 申请入口，都没有领取控件。
- **主界面左下角「目标」= 任务面板的直达入口**（实测客户区 (35,747)，有可领时带红色「!」），面板内容与 菜单→任务 完全同一个（底部同样是 日常任务/翻翻乐/成长挑战/赛季任务/家园目标 页签栏）。因此**不新建模块**，改为给 `hongbaolingqu` 加一条**兜底入口**：菜单路径要连中 `caidan`+`renwu` 两处模板，任一处失效就进不了面板，此时改点「目标」。
- **角落 HUD 图标的单击会被激活吞掉**（本轮卡了很久的真因）：`twice=False` 点「目标」「世界」「菜单」全部**毫无反应**，改 `twice=True` 立刻生效。两条新兜底入口都按「连点两下 + 用面板锚点确认 + 重试」写，不靠「点了就当进去了」。
- 顶部**活跃度里程碑宝箱**（20/40/60/80/100 五档）实测逐个试点**全部无弹窗**（当天已领），说明试点对已领档位无害；但正向样本今天造不出来，**没有实装这段扫描**，只把坐标记进交接笔记，等有未领的那天一并验证（见 `doc/LIVE-DEBUGGING.md` §5 的「检测器要用正样本验证」）。
- 测试：新增 `tests/test_haoyoujiangli.py`（3 条：点到按钮消失、上限截断、**兜底入口必须加客户区原点**且重试不漂坐标）+ `tests/test_hongbaolingqu.py` 追加 2 条（菜单失败后确实走兜底、兜底点位换算成整屏坐标）。反向验证：把兜底接线拆掉，用例立刻失败。

#### 翻翻乐自动烧钥匙（新增 `fanfanle.py`，并推翻「要长按」的假设）
- **机制实测**：一次单击不是 +1，而是**连抽到本轮 100 满**。进度 54/100 时点一次 → 钥匙 265→219（−46）、进度归 0；再点一次 → 钥匙 219→119（−100）。卡面翻出 III 奖励、里程碑积分 +100，**全程无弹窗、静默入账**。
- **长按假设作废**：之前记的「点 3 次进度仍 0/100，推进机制未确认」是**判据选错**——进度数字每满 100 归零，看它就像「点了没反应」；换成只减不增的**钥匙余量**后，一次点击的效果立刻可测。所以不需要长按，也不需要给点击 IPC 加时长字段。
- 实现沿用英雄厅堂的同一条无 OCR 判据：点击前后对「当前剩余：🔑NNN」区域自匹配。**阈值经实测修正为 0.90**：稳定帧自匹配 1.000，但刚进页面的过渡动画期间实测掉到 0.964–0.975——原来的 0.97 正好压在噪声带里，会把「页面还没停稳」误判成「钥匙已烧」；数字真变化时分数远低于 0.90（进度区域同法实测 0.428）。**必须 `twice=False`**：连点两下等于白烧一整轮 100 把钥匙。
- 新模板 `zengjiajindu.png`（214×30，按规范避开右上角「!」角标）标定实测：翻翻乐页 **0.983**、主界面负样本 **0.445**、实点落点客户区 **(819,741)** 正落在按钮中心。
- GUI 新增「翻翻乐」功能项与「最多轮数 (1-50)」输入框（默认 10，每轮最多 100 把钥匙）。实机跑 `main(max_rounds=1)` 全链通过：菜单→任务→翻翻乐页签→点击→判据命中→回主界面，余量实测 119→19。
- 新增 `tests/test_fanfanle.py` 5 条：余量不变即停、按轮计数、按钮消失不拿 None 坐标乱点、**必须单击**、轮数上限夹住。
- 踩坑修正：`_enter_fanfanle` 点完「任务」立刻找页签会扑空（面板有打开延迟），改为带 `timeout=4.0` 轮询——第一次实跑就是在这里报「任务面板里没有翻翻乐页签」。

#### 英雄厅堂自动快速升级（新增 `yingxiongtingtang.py`）
- 底部「快速升级」点一次即 +1 级（实测 650→651→652→653，全员等级与总战力同步上升），**没有确认弹窗也没有「获得奖励」弹窗**，无法靠弹窗判断成败。改用「等级数字区域点击前后的模板自匹配」：静止时连续四帧稳定 1.000，升一级掉到 0.918–0.943，阈值取 0.97；并轮询最多 3 秒再判定，避免撞上跳字动画误停。
- GUI 新增「英雄厅堂」功能项，配置面板带「快速升级次数 (1-99)」输入框（默认 10）。实测点满 3 次的上限时，第 3 次检测不到变化即自动停止（共鸣资源用完），行为符合预期。
- **不自动点「初识之人」红点**：那是公会结社科技树（万星结社 / 弑律 / 律法），实测进入后底部「升级」是灰的（资源 980/2000 不足），且选哪个节点决定公会玩法加成方向，属于要人决策的项。

#### 红点领取补全
- **赛季挂机关卡产出宝箱**（页面中部金箱）：点开→点「收获奖励」。实测收获是**静默入账**（无弹窗），领完宝箱变关闭态并重新计时，所以只能靠模板判断：满箱 1.000 / 空箱 0.450。收获按钮**复用既有 `shouhuojiangli.png`**（挂机奖励任务 v1.4.3 起在用，155×33），实测在赛季挂机关卡的收获面板上命中 0.992，无需新增第二张同义模板。
- **愿望单左上进度礼盒一直没领到——是真 bug**：旧实现用「愿望单标题锚点 + 偏移 (120,40)」点礼盒，实测落点在客户区 (538,71)，而礼盒中心在 (486,56)，**偏右约 55px 点在空白处**。修正偏移为 (68,25)，并优先用礼盒模板直接命中（可领 1.000 / 已领 0.693，阈值 0.85），其它档位外观不同时退回偏移兜底。
- **主界面右侧竖排三个图标勘察结论（逐个点开确认，均无独立奖励源）**：
  - **旗帜**：打开的是玩法目录「活动」页，与目录入口是同一个页面的重复快捷键，活动列表本身的角标筛选已被否决（见下条）。
  - **兜帽人物**：好友面板，页内即「一键赠礼并收取」——既有 `yijianzengli.png` 在该面板命中 **0.995**，说明「好友奖励」模块（菜单 → 社交）早已覆盖此入口，不必新增第二个入口。
  - **握手**：按客户区 (1527,672) 点开后截图仍是主界面（角色与「互动(F)」提示在位），没有出现独立的可领奖励面板，判定为互动/邀请类提醒入口，无领取动作。
  三者都不纳入自动领取；「好友奖励」那条走原模块即可。
- **活动卡片角标检测第六次否决**（记录以免再试）：卡片尺度角标与页签尺度不同，19px 模板在整屏只命中页签角标（0.99）；把模板按 1.0–1.7 缩放扫描后，**所有尺度仍然锁定在页签角标上**，卡片角标一处都抓不到。因此活动列表的可领筛选仍无可靠判据，未纳入自动领取。

#### 红点奖励领取（新增功能 `hongbaolingqu.py`）
- **覆盖范围（四个入口）**：
  1. 菜单 → 任务面板：每日任务 / 公会任务 / 成长挑战 / 赛季任务（二级 玩法·活跃·限时·养成·剧情 + 底部 阶段目标·赛季成长任务·赛季阶段）/ 家园目标；
  2. 主界面「赛季手册 → 赛季里程碑」；
  3. 主界面「赛季月桂之旅」（原记录称入口在右侧 HUD 1550,610，该说法已被第三批复测推翻：真入口是菜单第二行第 4 张卡片，客户区 (905,625)），进入后逐个切底部手记页签（480/630/780/880/990 @ y=845）领取；
  4. 主界面「当前进度 → 赛季挂机关卡」：先点右上角「x440」挂机收益（实测即弹「获得奖励」），再按 54px 栅格逐点里程碑节点，只把弹出奖励的计入。
  每个界面反复点「一键领取」与带勾选圆标的单个「领取」直到两者消失，弹「获得奖励」就点空白关闭；单界面 `MAX_CLAIM_PER_VIEW=30` 防死循环。流程末尾强制 `recover_to_main_interface()`，不把子页面留给下一个任务。
- **实测**：多轮实跑累计领取 8 项（赛季任务-玩法 一键领取 60 钻石 + 35000 药水、赛季积分 2533→2548；弦月之礼第 6 天 x3 门票；月桂之旅一键领取 2 门票 + 5000 金币 + 11000 药水 + 20 紫尘；里程碑 1241 节点；挂机收益 x440）。单轮 53.7–191.3 秒，跑完回到主界面。
- GUI 新增「红点领取」功能项，与「日常任务」互补（后者只点每日/公会的一键领取）。启用状态只由左侧勾选，`daily_reset` 字段已在同批 GUI 改造中整体移除。
- **两条试过又撤销的路径**（结论比代码更重要，记在这里免得下次再踩）：
  - **通用礼包角标检测**：同一枚角标按界面缩放，HUD 上还有脉动动画——实测同一 19px 模板在 目标 / 当前进度 / 玩法目录 三处只有 1.0 / 0.709 / 0.469；改成只取中心字形仍分不开「礼包」与「!」提醒角标（互相 0.95+）；换 HSV 圆形色块检测又会命中卡面上的橙色徽章。最终只在**面板内**用全尺寸角标（实测 1.0），入口一律不靠角标。
  - **玩法目录卡片盲栅格**：按固定卡片坐标逐张进「公会玩法 / 活动」再领取。实跑会误闯「纷战争锋」这类带自动派遣倒计时的活动页，且各页返回箭头素材不统一（`exitck` 在卡片详情页只有 0.283），恢复链反复失败、最后把游戏留在子页面。已整段撤销；这些玩法本就有专门模块（结社战线、狩猎悬赏）。
- **明确不覆盖**：背包 / 图鉴 / 旅行指南等「新」角标（新内容提示，无可领奖励）；赛季阶段排名的「首通」角标（点进去没有领取项）。
  当时还列了翻翻乐（「点 3 次进度仍 0/100，机制未确认」）——**该结论已在 11-04 被推翻**，
  是判据选错（进度每满 100 归零），翻翻乐现由 `fanfanle.py` 单独覆盖，见本节开头。
- **新增 13 张模板**：`richangrenwutab` / `chengzhangtiaozhan` / `saijirenwu` / `jiayuanmubiao`（任务面板底部页签灰字）、`wanfa`（赛季任务二级页锚点，其余按 132px 等宽偏移复用）、`jieduaimubiao` / `saijichengzhangrenwu` / `saijijieduan`（赛季任务底部页，注意页签有选中/未选中两套外观，采的是未选中态）、`saijishouchuoicon`（赛季手册图标本体）、`saijilichengbei`（赛季里程碑标题）、`lingqu`（单个领取）、`guajiguajia_locked`（里程碑未解锁节点，用于取节点行 y）。

#### 推图连续失败上限
- `push.PushFlow` 新增 `max_consecutive_failures`（默认 10，范围 1–99）：失败次数**跨阵容累计**，`end(k)` 成功推进后清零；达到上限时记录 `LAST_STOP_REASON = "fail_limit"` 并退出。配置位于 `push_settings.max_consecutive_failures`，GUI 推图参数面板新增「连续失败上限」输入框，幻灵推图 / 推图 / 循环推图共享；循环推图命中上限时整体停止，不再无限换阵容重试。
- **循环推图语义澄清**：每轮固定先幻灵、后普通，两种都跑完才进入下一轮；单个模式失败/异常会继续跑本轮另一种、下一轮仍从幻灵开始。停止条件为 F9、任一模式命中连续失败上限、连续 3 轮整轮 <30 秒；README 已按此改写。`LAST_STOP_REASON` 在调试模式与初始化提前异常时会先清空，避免误用上一轮的 `fail_limit`。
- 新增 `tests/test_push_fail_limit.py`：覆盖达到上限转退出、成功推进清零。

#### 新增每日任务：结社战线 + 狩猎悬赏（`jieshezhanxian.py` / `lieshouxunshang.py` / `flow_gonghui.py`）
- 两个公会日常任务登记于 `scripts` 列表与 `_run_script_dispatch` 分发表，默认执行顺序排在「异界迷宫」之后、「家园愿望单」之前（顺序现由功能列表拖动决定，见上节）。
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

#### 新增每日任务：家园愿望单（`yuanwangdan.py`）
- 新任务「家园愿望单」（启用状态由左侧勾选决定；旧的「完成即停用」已移除），登记于 `scripts` 列表、`_run_script_dispatch` 分发表与 `script_order` 执行顺序。**执行顺序置于末尾**：该任务在家园视图内执行，结束后游戏停留在家园，而项目其余流程以主界面「玩法目录」(`wanfamulu`) 为起点判定，排在中部会阻断后续所有任务。
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

### 判据与流程修正（实机修复）

#### 主界面判据修正（影响所有任务衔接，本轮最重要）
- **问题**：`recover_to_main_interface()` / `ensure_main_interface()` 用「底部玩法目录图标 wanfamulu」判定已在主界面，但**英雄厅堂、玩法目录子页的底部栏里有同一个图标**。实测任务停在英雄厅堂时 recover 直接判定成功返回，随后所有按 HUD 坐标点击的入口（赛季手册 / 月桂之旅 / 当前进度）全部落空，日志表现为「点击后仍在主界面」——这正是最初「上一任务没退干净导致下一任务从错误界面开始」的同类病根。
- **修法**：新增 `common.at_main_interface()`——玩法目录可见 **且** 没有 `exitck`/`fanhui` 返回箭头才算主界面；`recover_to_main_interface`、`ensure_main_interface`、`hongbaolingqu._is_at_main_interface` 全部改用它。
- **验证**：修前同一场景三个入口 0/3 进入；修后同一次实跑三个入口全部进入并领取（月桂之旅 1 项、赛季挂机关卡 2 项），跑完 `at_main_interface()` 为 True 且快速升级按钮不再可见。

#### 实测中修掉的四个既有坑
- **窗口激活后立刻点击仍会被吞**：`ensure_game_clickable` 调 `_activate_game_window` 后没有等待，激活是异步的，这一次点击仍可能被正在发生的窗口切换吃掉（实跑「菜单 → 任务」第一步就复现）。改为激活后 `sleep(0.25)`。
- **面板记住上次页签导致锚点失效**：任务面板会从上次浏览的页签（实测翻翻乐）重新打开，而页签选中态会变绿——`fanfanle.png` 选中后只剩 0.724 分，用它当「面板已打开」锚点会误判成没进去并反复重点菜单。现改为对 4 个未选中态灰字页签做或判断，并在进入后**显式点回每日任务**，避免漏扫。
- **返回箭头素材不统一**：任务面板 / 赛季手册 / 玩法目录列表是 `exitck`（0.991，此处 `exit`/`fanhui` 只有 0.42），活动与公会卡片详情页却是 `fanhui`/`exit`（`exitck` 只有 0.283）。新增 `_click_panel_back()` 按候选依次尝试。
- **半透明 HUD 标签不能做模板**：「赛季手册」文字标签是压在场景上的半透明药丸，镜头换背景后从 1.0 掉到 0.767；改用不透明的图标本体（带流光仍 0.965）。同理「当前进度」入口只能按客户区固定点位点击，再用「主界面 HUD 是否消失」判定是否真的进了面板（面板类锚点会随子页变化失效）。

#### 女神塔 / 迷梦之域衔接修复
- **女神塔「一键碾压」**：部分层数会在「开始挑战」位置显示「一键碾压」按钮，导致找不到 `zhandou` 而中断。新增 `wait_for_battle_start()`，同时轮询 `zhandou` 与可选的 `yijiannianya.png`，命中碾压按钮时点击并继续等待结算/下一层。
  - 该模板需按实际界面补图（当前仓库没有）：未放置 `templates/yijiannianya.png` 时只等待普通战斗按钮，日志会提示一次；模板检查测试已将该文件登记为可选模板。
- **迷梦结算/战绩页清理**：新增 `ensure_back_to_challenge()`，战斗后不仅点「点击空白处关闭」，还会尝试 `exitck` / `exit`，直到重新看到「挑战」按钮；`handle_battle()` 现在把清理结果作为成功条件，避免带着战绩页进入女神塔。

#### 实测发现并修复
- **狩猎悬赏面板加载竞态**：标题先于卡片/按钮渲染，`_enter_panel` 看到标题就返回，随后 `timeout=0` 的检测直接判空，首次实测出现「搜寻 0 次、加入 0 次」。现在等待搜索/加入按钮就绪（最多 6s），两处按钮检测也改为带短轮询。修复后实测成功搜寻并参加队友悬赏。
- **家园愿望单从公会大厅启动失败**：上一个任务（结社战线/狩猎悬赏）结束时可能停在公会大厅，而大厅底部同样显示「玩法目录」，旧的主界面判定会误认为已在家园，导致找不到左侧「愿望单」入口。`_ensure_panel` 现在找不到入口时先尝试 `fanhui`/`exit`/`exitck` 逐层返回家园再重试。
- **家园愿望单补货链路修正**：实测发现旧实现假设「点途径箭头 → 直接到制作界面」，实际是「自动寻路 → 点角色脚下 F 交互提示 → 生产选择页点『愿望单需求』卡片的『选择』→ 制作界面」；开始按钮也分建筑（厨房「开始烹饪」/锻造「开始锻造」，炼金模板可选）。已新增 `xinyuandanxuqiu.png` / `kaishiduanzao.png` 模板并落地对应流程；数量档、开始按钮、交互提示、选品全部改为单击——`click_position` 默认连点两次会把 x10 多点回 x1。
- **制作原料不足守卫**：点击「开始」后若弹出「当前资源不足」，弹窗会遮住按钮，旧逻辑会把「按钮消失」误判成制作已开始并白等 600 秒。现在弹窗出现即记录「所需原料不足」、关闭弹窗并结束补货。
- **循环推图模式间恢复**：实跑发现幻灵推图战斗结束后可能停在「战斗失败」页，`wanfamulu` 不可见，导致本轮普通推图与后续轮次都卡在入口等待上空转。新增 `_ensure_loop_ready()`：每轮开始及模式切换前先清弹窗、逐层返回主界面；`push.py` 的入口等待也补 `recover_threshold=20`。修复后实跑验证：幻灵推图停在失败页 → 自动回主界面 → 普通推图成功进入；普通推图连续失败达到配置上限 10 次后循环整体停止（总耗时 614 秒）。
- **幻灵推图入口首次点击丢失**：实跑出现点击「幻灵挑战」后未确认进入备战页，手动点同一位置可进入。原因是游戏窗口不在前台时，系统会把第一次点击用于激活窗口而吞掉；`ensure_game_clickable` 改为只要游戏不在前台就先激活（不再只判断点击点是否被遮挡），并给 `push` 模式入口加一次重试（重新找入口、仍只单击）。修复后重跑成功进入并完成一轮幻灵推图（705.9 秒，途中打赢多关）。
- **end(k) 排查结论**：历史日志里同一坐标（客户端 800,225）的 `end(k)` 点击曾多次成功（点完立即出现模式入口），最近两次失败与「游戏不在前台时第一次点击被激活吞掉」同源，`ensure_game_clickable` 的前台激活修复已覆盖该根因（修复后两次实跑的入口点击均一次确认成功）。另加结果页兜底：点击后 10 秒仍未确认入口且 `end.png` 仍可见时，点左下角返回箭头退出结果页再确认；确认失败才结束。受当前账号连续失败（10/10）影响，`end` 路径尚未再次触发，待下次胜利段实跑验证。
- **repeat(e) 同样会丢首次点击**：上一轮实跑在 6 次失败时点击 `repeat(e)` 成功但 10 秒内没确认到推图/阵容界面，整轮推图被提前判定失败结束。新增 `_click_repeat_and_confirm()`：确认后看不到目标界面时，**只在失败页仍在**的情况下补点一次（界面已经变化就不再盲点，避免点到不存在的位置）；连续失败上限分支也补一次同样的重试，尽量自己离开结算页而不是带着失败页进入退出流程。
  - **实测验证**：15:15:35 第 6 次失败的 `repeat(e)` 点击被吞（12 秒后 `fail.png` 仍在）→ 日志「点击 repeat(e)(1) 后失败页仍在，重试点击 repeat(e)」→ 补点后立即回到推图界面并继续战斗，最终按配置上限 8 次正常结束（`ok=True reason=fail_limit elapsed=178.0s`，回到主界面）。同轮其余 7 次 `repeat(e)` 均一次确认成功。
- **推图点击容错补齐单测**：`tests/test_push_fail_limit.py` 增加 4 个用例——`repeat(e)` 被吞后补点、已离开失败页时不盲点、`end(k)` 结果页兜底走返回箭头、结果页已消失时不再补点。
- **实测记录**：结社战线（进入→挑战→失败结算→扫荡次数为 0→清理回主界面）通过；狩猎悬赏（搜寻至 0/15、参加队友悬赏）通过；家园愿望单（交付 1 单、领奖、寻路、选品）通过。当前账号原料不足以启动 x10 制作（弹窗指向 18 级元素精炼所生产元素精华），因此**完整制作耗时仍未实测**；遇到二级原料不足会安全结束，原 pending 项继续保留。

#### 家园愿望单修复：模板按 1600×900 重采 + 偏移量重标定
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

#### 新增：卡死自动兜底回主界面（防连锁卡死）
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

### 实机勘察结论

#### 活动页与其余入口勘察（用户要求「继续找还有没有能领的」）
- **惊秋之夜（钓鱼联动活动）领到 2 项**：竞技场 6/6 任务「一键领取」（累计进度 720→820）+ 过 800 档的里程碑卡（点击后弹「获得奖励」）。导航链：菜单 → 活动 → 惊秋之夜卡片。
- **纷战争锋不需要动作**：进去是「欢迎回来 / 您已离开13小时1分」的战报结算页，「进入活动」上的「!」只是提示可改阵容；底部写明「20:14:33后自动派遣」，派遣与积分本来就自动结算，战报里没有任何领取按钮。**没有点「调整」**——那会改动用户的队伍配置。
- **钓鱼判为暂不可自动化**：「获取秘钥」页只有任务清单（钓15条→x10钥匙、金冠鱼5条→x22，均可重复完成），真正的钓鱼要跑图到钓点且是上钩小游戏；而 `send_coord` 的 IPC **只传坐标、不能滚轮也不能拖拽**，连需要滚动的玩法目录长列表都浏览不到底。已作为方法学记入 `doc/LIVE-DEBUGGING.md` §5.2。
- **坐标纪律**：菜单里「活动 / 商城」两张卡挨得很近，按估读坐标 (748,545) 点进去实际落到**商城**，导致一整轮「7 个活动页签探测」全在同一页上跑空。改用**带 100px 网格的截图**读坐标后修正为 (680,505)。教训：固定点位必须先截图核对，不能凭肉眼估。
- 神秘屋（挂机关卡旁的入口）= 神秘珍藏 / 金玫瑰高定 / 月桂酒馆 / 商店，全是商店与招募，无可领项。

### 日志、GUI 与工程化

#### 日志格式统一（新增 `log_format.py`）
- **只在出口整理一次**，不去改三十个流程模块里的 print：GUI 的 `log()` 与 `_StdoutTee` 两条路都过 `format_body`。做三件事——任务运行期间的细节行缩进加 `·` 归到该任务下（以前「命中 caidan」根本看不出属于哪个任务，只能往上翻找「开始执行」）；高频行压短；任务边界单独成行。
- 压缩只认**整行就是这个形状**的四类（实测一份日常日志里 命中 717 行、未命中重试 1322 行、状态跳转 617 行）：`X 识别成功，第 N 次，坐标: (x, y)，发送给 AHK 点击` → `命中 X (x, y) 第N次`；`X 第 N 次未找到，0.5 秒后重试（已等待 s 秒）...` → `未命中 X 第N次（已等 ss）`；`X 在 t 秒内未出现，放弃等待。` → `放弃 X（ts 内未出现）`；`a -> b` → `状态 a → b`。**没命中的行原样通过**，一个字符都不改。
- 顺带修掉一个老毛病：面板以前收的是逐次 `write` 的碎片（print 分正文+换行两次调用），文件收的是整行，两边看到的不一样；现在统一按行缓冲，**面板与文件同一份正文**，各自补时间戳（不会双戳）。
- 过程中被自己的渲染样例抓出两个真错：① 边界行是在 `set_task` 之后打的，被自己的缩进规则吃成 `· ▶ [1/3] 邮件`——改为 `▶ ✔ ✘` 开头的行永远顶格；② `【普竞】renwu 在 5.0 秒内未出现` 被压成 `放弃 【普竞】renwu（…）`，标签嵌进了短语中间——改为把 `【模块名】` 留在行首，且**只有真的压缩了才重排**，否则整行原样。
- 验证：`tests/test_log_format.py` 10 条（四类压缩、未命中行原样通过、任务内缩进、清任务后回顶格、边界行顶格、标签留在行首、空行、边界行形状）；并用真实 GUI + tee 跑了一遍接线，确认面板与文件渲染一致且无交付双时间戳。全仓 ruff 回到基线 64（新增的 I001 导入排序已修）。

#### 日志
- **子脚本日志之前根本没落盘——这是「日志方便调试」的真正缺口**：`game_bot.log` 里只有 GUI 自己的行（开始/完成/耗时），各流程模块经 `common.log()` 输出的识别与领取细节一条都没有（实测用户今早跑完整一轮后，全文搜「家园愿望单」只剩两条 GUI 行，`【家园愿望单】…` 一行都搜不到；`common.log()` 在有 sink 时特意不再 `print`，而 sink 只接了 `_enqueue_log`＝只进界面面板）。改为 `common.set_log_sink(self.log)`，一条子脚本日志同时进面板和文件。反向验证：把 sink 改回 `_enqueue_log` 后新增的两条用例全部失败。
- **测试不再污染用户日志**：GUI 测试构造 `GameBotGUI` 时，`__init__` 里那句「已注册全局热键」早于各用例自己打的 `log` 补丁，直接写进项目根的 `game_bot.log`——实测**跑一次 pytest 追加 10 行**，累积下来这份文件里有 300 条该噪声（占全文近一半），把真正要看的识别/领取记录埋掉。`tests/conftest.py` 新增会话级 autouse 夹具，把 `bot_runtime.LOG_FILE` 整体指向临时目录并在会话结束还原；复测同一轮 pytest 前后计数不变（310 → 310），用例全绿（34 → 36）。
- **子脚本行补时间戳**：`game_bot.log` 本来就会落盘（UTF-8、5MB 轮转、含全部识别行），但 GUI 行带 `[HH:MM:SS]` 而子脚本 `print` 的行不带，调试时看不出「识别失败 12 次」是同一秒抖动还是跨了半分钟。`_StdoutTee` 改为按行缓冲（`print` 会分正文+换行两次调用），凑齐一行再写一条带时间戳的日志；新增 `tests/test_log_timestamps.py` 守住「每行都有时间戳」和「一次 print 只产生一行」。

#### GUI：列表内勾选启用 + 状态颜色标注，且不再自动改启用
- **状态颜色**：功能列表每行勾选框右侧加一枚状态色块，随运行实时刷新——蓝=运行中、黄=排队中、
  绿=完成、红=失败/错误、灰=F9 停止，未跑过的行留空。此前状态只存在于运行日志里，
  要翻日志才知道跑到哪、哪个挂了。配色用 `tk.Label` 的 `bg`：Windows 的 vista 主题会忽略
  `ttk.Button` 的 background，只有经典 tk 控件能真正变色（`STATUS_COLORS` / `STATUS_NEUTRAL`）。
- **启用勾选框进列表**：每行行首一个 `tk.Checkbutton`，改动即写 `enabled` 并立即持久化；
  删除配置子页里的「开启」勾选框与列表的 `✓ ` 文本前缀——同一状态此前有两份表达，
  用户看不出哪个算数。
- **完成后不再自动取消勾选**：移除 `daily_reset`「成功即停用」行为，并把这个随之变成死概念的
  字段整体删掉（`ScriptConfig` 参数、9 处构造、`load_config` / `save_config` 键、
  三个流程模块 docstring 里的「daily_reset」表述）。旧行为会把用户设置写回配置，
  导致第二天该任务被静默跳过，且用户再打开时看到的是被程序改过的勾选。
- **拖拽排序的连带改动**：一行现在是「勾选框 + 色块 + 名称按钮」三段，落点判定与重排
  改为对行 `Frame` 操作，`scripts / script_rows / script_buttons / script_checks /
  script_status_labels / script_enabled_vars` 六份集合必须同序换位；列表画布宽度
  150→205、按钮 15→13 字符，否则名称被裁成「挂机奖…」。
- **测试**：新增 `tests/test_gui_status_display.py`（5 例：状态值全覆盖、色块文字/底色、
  勾选框 invoke 走真实 command 链路并落盘、重排后六份集合同序、勾选状态能原样读回）。
  新增 `tests/conftest.py` 提供会话级唯一 Tk 根——两个 GUI 测试模块各建一个根时，
  后建的那个稳定抛 `TclError`，导致 4 个用例被 skip（实测复现）。
- **实机确认**：真起 GUI 跑 mainloop，按窗口标题抓图核对——六种颜色都渲染、
  名称完整不被裁、勾选框反映持久化的用户设置。

#### 远程桌面兼容：后台截图 + 点击前自动激活（`common.py` / GUI）
- **问题现象**：主桌面运行正常，远程桌面（单屏、分辨率不同）运行会点到不该点的地方；迷梦→女神塔等任务衔接时也可能从错误界面开始。
- **根因**：①远程桌面通常只有一个屏幕，机器人窗口盖住游戏，屏幕截图拿到的是机器人界面、坐标点击也落在机器人窗口上；②不同会话/缩放下 DPI 虚拟化会让 `GetClientRect/ClientToScreen` 与物理像素截图错位；③窗口位置在切换分辨率后变化，旧的客户区缓存失效。
- **后台截图**：新增 `windows-capture`（Windows Graphics Capture）可选依赖。WGC 由 DWM 直接合成目标窗口画面，**游戏被其他窗口遮挡时仍能识别**（实测遮挡前后模板命中坐标一致）；不可用时自动回退普通屏幕截图。截图仍是「全屏坐标系」，所有 `find_center` / 点击坐标语义不变。
- **点击前自动激活**：`send_coord` 写入坐标前用 `WindowFromPoint` 判断点击点最上层窗口；被遮挡时把游戏窗口切到前台（含 `AttachThreadInput` 与前台锁兜底），避免点到机器人自己。可通过控制栏「远程桌面兼容（后台截图+自动激活）」整体开关，默认开启。
- **坐标稳定性**：进程启动即声明 Per-Monitor DPI 感知；`game_client_region` 每次调用都重新校验窗口矩形，远程桌面切换分辨率/拖动窗口后不会沿用旧坐标；启动任务时若客户区不是 1600×900 会打印明确警告。
- **构建**：`goldenhandmaidens.spec` 显式加入 `windows_capture` hiddenimport；README 依赖补 `windows-capture`。未安装该依赖时功能仍可用（回退前台截图 + 自动激活）。

#### 运行日志与任务状态增强
- 控制栏新增「当前任务」标签（如 `女神塔 (3/12)`），窗口标题同步显示；任务开始/完成/失败日志带 `[序号/总数]` 与耗时（秒）。
- 任务异常时面板记录首行原因，完整堆栈写入 `game_bot.log`，便于远程反馈定位。
- 启动运行前打印截图模式与自动激活状态，并校验游戏客户区尺寸。

#### GUI：功能列表可拖拽排序 + 支持单独运行一个功能
- **拖拽改执行顺序**：功能列表按钮支持按住上下拖动重排（位移 < 8px 仍视为普通点击，不进入拖拽，避免误改顺序）。关键是消除了「两份顺序数据」——原先执行顺序由 `run_scripts_thread` 里一份硬编码 `script_order` 常量决定，按钮列表只是它的镜像，拖动改了也不生效；现在 `run_scripts_thread` 直接按 `self.scripts` 迭代，列表顺序即执行顺序。重排后按名字找回 `current_script_index`，避免右侧配置面板跳到别的功能上。
- **顺序持久化**：`save_config` 写入 `script_order`（功能名列表），启动时恢复；配置里没有的功能（新版本新增）按默认顺序补到末尾，不会因升级丢顺序也不会漏项。
- **单独运行**：配置面板新增「只运行当前功能」按钮（`run_single_script`），只跑选中的那一个功能并忽略其它勾选，用于逐项验证或补跑漏掉的一天。与「全部运行」共用新的 `_begin_run(scripts, respect_enabled)`，运行态复位 / 状态标记 / 线程拉起只有一份实现。原先 `start_all` 在「没有启用任何脚本」时先置了 `is_running` 再 `stop_all` 回滚，现改为校验不通过直接返回，不再留下一次多余的停止日志。
- 拖拽松手时 ttk `Button` 的 `command` 也会触发，会把「调整顺序」误当成「选中该功能」；用 `_drag_moved` 标志抑制，且该标志延迟到下一次按下才复位（command 与 `<ButtonRelease-1>` 回调的先后顺序不保证）。

#### 隐藏启动/关闭时的黑色控制台窗口
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

#### 隐藏启动/关闭时的黑色控制台窗口
- 根因：PyInstaller 控制台模式为 `print()` 分配 Windows 控制台。`goldenhandmaidens.spec` 本就是
  `console=False`，但原 `sys.stdout` 重定向仅在点击「开始」后设置，窗口模式启动期 `sys.stdout=None` 有崩溃隐患。
- 修复（`Goldenhandmaidens.py`）：`main()` 首行即接管 stdout（`_StdoutTee`），启动前 print 缓冲、GUI 建好后
  灌入面板；退出重置改为 `_StdoutTee(self._enqueue_log)`。
- 重新打包引导器选 `runw.exe` 窗口版，根 `goldenhandmaidens.exe` 已更新为无控制台；日志仍进「运行日志」面板，
  `click_from_file.exe` 早已 `CREATE_NO_WINDOW` 隐藏。

#### 功能面板：一键全不选
- 配置面板「开启」勾选框旁在「一键全选」基础上并排新增「一键全不选」按钮，调用 `GameBotGUI.disable_all_scripts()`：
  一键将所有功能脚本 `enabled` 置 False（仅改启用状态，不动各脚本的参数），刷新当前面板勾选框与列表 `✓` 标记并持久化到配置。

#### 重新打包 exe 与清理冗余
- 用 PyInstaller 6.22.0 + `goldenhandmaidens.spec` 重新打包，根目录 `goldenhandmaidens.exe` 已更新
  （含本轮全部源码改动：日志队列节流、`find_center_silent` 统一、任务字典分发、停止检查加固等）。
- 删除游离测试脚本 `test_hero_match.py`（未被任何模块引用）。
- 打包生成的 `build/`、`dist/` 临时构建目录已清理，仅保留根目录新 exe。

### 测试、依赖与代码质量

#### 补纯逻辑测试（B3：四个零测试模块）
- 用例 **60 → 106**。新增 `tests/test_yuanwangdan.py`(18) / `tests/test_warehouse.py`(9) / `tests/test_flow_migong.py`(12) / `tests/test_flow_tower.py`(5)，并给 `tests/test_smoke.py` 补 2 条阵容判定用例；只测决策逻辑，不碰像素阈值。
- **愿望单**：`_panel_state` 的判定优先级表（领奖 > 不足 > 交付 > 一键 > 结算），含「只有『点击空白处关闭』提示命中也算结算」这条兜底判据（`yuanwangdan.py:171`，当初因结算标题流光动画 0.82–0.95 抖动才改的设计）；`_wait_gone` 的超时语义（含 `timeout=0` 时仍做最后一次确认）；`_claim_reward` 礼盒模板跨不了档时退回「锚点 + 偏移」的兜底坐标。
- **仓库扫描**：`_iter_scales` 的 `step<=0` 空产出与 `+1e-9` 上界容差；`_best_multiscale_match_score` 的退化输入必须返回 `-1.0` 而不是崩在 `cv2.resize`；`has_fancy_border` / `_top_band_edge_count` 只吃传入 ROI，可测则一并补上（纯色不误判为华丽边框）。
- **跨模块文本契约**：`warehouse._save_heroes_to_txt` 写、`flow_tower._load_warehouse_levels` 读，中间只有一条「名字,高/低/未拥有」的文本格式约定、没有共享代码——做了一组 round-trip 用例把它钉住（格式一变即静默丢练度，是本轮价值最高的一条）。
- **迷梦之役**：`cfg` 运行时参数压过文件配置 / 缺 key 回 default；`_pick_closest_mgzd` 的欧氏距离最近与空表短路（显式传 `[]` 不得回退查屏）；`find_all_instances_mg` 的阈值边界、`min_gap` 去重、按 y 升序；`handle_failure` 的清理序列与 `drag_repeat` 长按次数；外层循环次数耗尽后不再点 `jinru`。桩图固定在 20×24 量级——该函数是逐像素双层 Python 循环，真机 `res` 约 1596×896，用大图单条用例会跑到几十秒。
- **负验证**：46 条新用例逐条翻转产品判据验证，45 条变红。**1 条如实标注为无法负验证**——`find_all_instances_mg` 的 `loc.sort(key=y)` 在当前双层升序扫描下是恒等操作（发现顺序天然已按 y 递增），删掉也不会红；用例保留作 B11 向量化（`np.argwhere` 行序不保证）之后的防线，测试内已写明原因。
- **顺带修两处**：`yuanwangdan.py:309` 的 `_find(tpl_wish_label, 0.85)` 改为显式 `timeout=0.85`——**行为完全不变**，`_find` 第二个位置参数是 timeout 而非阈值，裸写极易误读成「阈值 0.85」（由新测试暴露；若将来真需要收紧该阈值，须实跑验证后另行改动）；`.gitignore` 的 `!requirements.txt` 改 `!requirements*.txt`，否则 `requirements-dev.txt` 被上一条 `*.txt` 吞掉、clone 后根本拿不到。
- **发现但登记未改**（都需要实跑或更大的改动范围，不在补测试分支内动）：`warehouse.has_fancy_border`（:469）**全仓无调用点**（主流程实际走 `_top_band_edge_count`，`flow_tower` / `push` 另各有一份 `has_fancy_border_lineup`），疑似遗留代码；零方差 / 纯色图上 `cv2.matchTemplate` 返回 **1.0** 而非报错，模板全黑时会「满分命中」；`flow_tower.py:84` 的 `SPECIAL_HERO_SET` 是空集，故其特殊角色分支实际不可达（只有 `push.py:68` 含 meimo/kululu/shizi），属配置而非缺陷。

#### 建立依赖清单（B1：新机器 clone 后跑不起来）
- 新增 `requirements.txt`（运行时）与 `requirements-dev.txt`（pytest / ruff / pyinstaller），全部按本机 **Python 3.13.17** 实盘 `==` pin；文件顶注写明用途与「只装一个 OpenCV 发行版」。
- **OpenCV 三发行版判定**：本机同时装了 `opencv-python` / `-contrib-python` / `-headless`，三者往同一 `cv2/` 目录互相覆盖。据运行时 `cv2` 同时含 contrib 独有模块（xphoto / bgsegm / SIFT / wechat_qrcode）与 GUI（imshow / namedWindow），且 `site-packages/cv2/cv2.pyd`、`cv2/__init__.py` 时间戳（2026-10-05）与 `opencv_contrib_python` 的 dist-info 一致、晚于另两个（2026-09-19）——判定生效者为 **opencv-contrib-python**，清单据此只保留它一个以精确复现本机行为（仓库实际未调用任何 contrib 模块，plain `opencv-python` 功能上也够，注释已说明）。
- **依赖分级**：`cv2` / `numpy` / `PyAutoGUI` 是 `common.py` 顶层 import 的硬依赖（缺失即崩）；`windows-capture`（后台截取遮挡 / 提权窗口）、`keyboard`（全局热键 F8/F9）、`certifi`（更新接口 SSL 根证书）三者在代码里都有 try/except 回退，属「可选但已在用」，已列入运行时清单并注明回退行为。`PyAutoGUI` 的传递依赖（pyscreeze / mouseinfo / msgpack / pyperclip / pillow）交给 pip 解析，不逐条 pin。
- **顺带查出两处勘察遗漏的隐藏依赖**：`keyboard`（`Goldenhandmaidens.py:1345` 函数内 import）、`certifi`（`updater.py:17`）——本机都已装，但原「第三方 import 仅 cv2/numpy/pyautogui」的结论没覆盖到，已补进清单。
- **清理过时文档**：README「二次开发」里 `pip install pyautogui opencv-python numpy pillow requests windows-capture` 有误——`requests` 全仓未 import（`updater.py` 走标准库 `urllib`）、`pillow` 只是传递依赖、opencv 应写 contrib；改为 `python -m pip install -r requirements.txt -r requirements-dev.txt`，并在「运行环境」补 Python 3.13 实测与 OpenCV 单发行版注意事项。**装了但没用**：`psutil==7.2.2` 全仓无任何 import，未列入清单。
- 验证：`python -m pip show` 逐条核对 9 个顶层包版本与清单一致（全程离线，未安装/升级/卸载）；`python -c "import common, cv2, numpy, pyautogui, windows_capture"` 通过（`cv2 5.0.0` / `numpy 2.5.3`）。

#### 审计遗留项收尾（A3 / A7 / A9 / A10）
- **模板一致性自动检查（A3）**：新增 `tests/test_templates.py`——扫描全项目 `get_template_path("x.png")` 字面量引用，断言每个引用都在 `templates/` 下存在；断言模板尺寸不超过 1600×900 客户区（超了说明是在别处裁的）；未被引用的模板只作信息输出（英雄模板按 ID 动态拼名，静态扫描看不到引用属正常）。
  - 该测试**立即抓到一个既有缺陷**：`warehouse.py` 引用的 `warehouse_title.png` / `warehouse_first_card.png` 在仓库里从未存在过（`git log` 查无此文件）。追查发现唯一使用者 `_locate_first_card()` **从未被任何代码调用**——是遗留死代码（内含「这里的偏移要你根据实际界面调」这类未完成注释）。已删除该函数与两个常量，`CARD_WIDTH` / `CARD_HEIGHT` 仍被其他逻辑使用故保留。
- **GUI 顺序测试产品化（A9）**：`tests/test_gui_order.py`（6 个用例）真实构造 GUI，覆盖重排后脚本/按钮顺序一致、选中项跟随原功能、`script_order` 持久化内容、配置缺新功能时补末尾、单跑目标、以及「位移 <8px 不算拖拽」。整模块共用一个 Tk 根（同一进程反复建根本会随机抛 `TclError`，实测导致用例间歇性 skip），配置文件重定向到临时目录，不污染用户配置。
- **日志轮转（A7）**：`append_log_file` 写入前检查大小，超过 5 MB 就把当前日志改名为 `.1`（只留一份备份）再新建。实测把已增长到 8.86 MB 的 `game_bot.log` 正常滚动，新文件重新开始。`.gitignore` 补上 `game_bot.log.*`，避免轮转出的备份被误提交。
- **补货制作完成等待上限 90s → 600s**：实跑复现了「制作完成等待超时」。查下来不是常量写小一点的问题——早先按 x1 档制作能在 90s 内完成并正常返回，改成「点两下数量档取 x10」后一次生产 10 份，实测 180s 仍不够。上一轮已修的「按钮必须先消失」判据是对的（本次实测确认按钮确实消失、制作真的开始了），问题只在上限。按已知下界把上限提到 600s；**仍未观测到一次完整的 x10 制作返回**，若后续仍超时，说明完成信号不是"按钮重新出现"，需要重新看制作结束后的实际界面。
- **整洁性批量清理（A10）**：删除 8 个文件首行残留的 `# F:\afkj\game-bot\xxx.py` 绝对路径注释；删除 `common.py` 重复的 `_ACTIVE_TEMPLATES_DIR = None`；`random_sleep()` 由 5 个文件各自的副本上移到 `common`（策略变更只需改一处），各文件随之移除未使用的 `import random` 与函数上方的孤儿注释；README 去掉写死的主文件行数、功能表补上公会玩法与家园愿望单两行。

#### 架构改进（依据 `doc/AUDIT-REPORT-2026-11-02.md` 的 R1–R5）
- **模板匹配限定到游戏客户区**（R1，实测提速 2.1–3.8x）：`find_center` / `find_center_silent` 在未显式传 `region` 时改用 `common.game_client_region()` 取到的游戏客户区（`GetClientRect` + `ClientToScreen`），返回值仍是全屏绝对坐标、语义不变。桌面 3840×1080 而客户区只有 1600×900，原先每次匹配要多扫约 3 倍像素：单次匹配 216–357ms → 73–106ms，端到端 `find_center_silent` 317ms → 149ms 且**命中坐标完全一致**。未命中时会刷新一次窗口矩形再试，兼容运行中拖动窗口；取不到窗口（非 Windows / 游戏未开）自动退化为整屏，行为与改动前一致。
- **点击器存活探测**（R2）：`click_from_file.exe` 长时间运行后会自行退出，此后所有点击静默落空、表现为「界面连续多轮无变化」——本轮就被它误导过一次诊断。新增 `clicker_alive()`（用当前光标位置作哨兵，避免把鼠标甩到角落）与 `ClickerNotRunning` 异常：`send_coord` 连续 3 次坐标无人消费即报错中止任务，GUI 在每个任务开始前也探测一次、失败则中止后续任务并写明原因。失败方向的取舍：宁可让任务报错（勾选保留、次日重跑），也不让"空转 8 轮后正常结束"把当日任务吞掉。
- **统一任务成败语义**（R3）：`_run_youjian` / `_run_haoyou` / `_run_pujing` / `_run_nvshenta` / `_run_guajijiangli` / `_run_shangcheng` / `_run_meiri` / `_run_pata` 原先全部硬编码 `return True`，其中 5 个流程的 `main()` 根本没有返回值。后果是**失败也会被记为「执行完成」**，而 `daily_reset` 脚本在"成功"后会自动取消勾选——当日任务被静默跳过。现 5 个流程的 `main()` 在任一步骤失败时 `return False`、走完 `return True`，8 个 runner 全部透传。`_run_login` 保持恒真并加注释说明原因（找不到开始界面说明游戏已在登录态，属正常跳过）。
- **统一弹窗关闭路径**（R4）：`dismiss_popup()` 改为复用 `dismiss_popup_away_from()`（点「点击空白处关闭」左上方空白），兜底点从**屏幕底部居中**改成**左下角**——实测底部居中与结社战线「扫荡」、狩猎悬赏「搜寻精怪」、愿望单「交付」重合（偏差仅 2–15px），任务间清理会误触发按钮。
- **配置与模板路径语义统一**（R5）：新增 `common.get_config_path()`（工作目录优先、打包内置回退），`formations.json` / `grid_offsets.json` / `migong_config.json` 改走它——原先走 `get_resource_path`（打包后指向只读的 `_MEIPASS`），用户改 exe 同目录的那份**不生效**。`start.py` 改用 `get_template_path()`，不再自行拼 `templates/` 路径绕过 APPDATA 副本机制。
- **新增测试**：`tests/test_clicker_guard.py`（6 个用例）覆盖点击器漏消费告警、`ClickerNotRunning` 触发阈值、正常消费不误报、客户区限定的坐标换算与区域外不误命中。全部 8 个用例通过。
- **新增 `doc/TEMPLATE-AUTHORING.md`**：把本轮多次事故的根因沉淀成规范——1600×900 采集、避开角标与流光动画、纯色块不可作模板、采完须同时验证"目标界面分 / 最易混淆界面分 / 实点落点"、以及「红点不一定是奖励」（实测可能是剧情对话）。

#### 仓库完整性修复：家园愿望单整个功能此前从未提交
- 核对 `git ls-files` 发现：上一轮只把 `yuanwangdan.py` 和它的 README/CHANGELOG 说明写进了工作区，**代码文件和它依赖的全部模板都没有 `git add`**（`yuanwangdan.py`、`yuanwangdan.png`、`yijianxuanze.png`、`xinyuandanjiaofu.png`、`xinyuandanwancheng.png`、`xinyuandanbuzu.png`、`xinyuandanbiaoti.png`、`tujingjiantou.png`、`kaishipengren.png`、`fanhui.png`、`huodejiangli.png` 均为 untracked）。也就是说 clone 仓库的人既看不到这个任务、跑起来也会 `ValueError: 模板读取失败`。本次连同新增的公会玩法模板一并纳入版本库。
- 教训：新增任务脚本必须和它的 `templates/*.png` 一起 `git add`；只提交 `.py` 等于提交了一个跑不起来的功能。收尾时用 `git ls-files` 对照代码里的 `get_template_path(...)` 清单，比凭记忆可靠。
- `.gitignore` 补齐：`goldenhandmaidens.exe`（打包产物，92MB；`click_from_file.exe` 是运行依赖仍需入库）、`game_bot.log`、`.codebuddy/`、`.workbuddy/`、`_tmp_*`、`_devshots/`。

#### 代码审查优化（全面 review）
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

#### 代码审查后续：落实 3 项建议
- **统一 `find_center_silent`**：`common.find_center_silent` 合并 `push.py` 之前自带的轮询副本，新增
  `timeout` / `interval` 参数（默认 `timeout=0` 单帧检测，向后兼容其余 7+ 个 flow 脚本的 `region` 调用），
  循环内调用 `check_stop()`。`push.py` 删除本地重复实现，改为薄包装 `find_center_silent(..., timeout=3.0)`
  保留原「最多轮询 3s」语义。消除两份逻辑分叉。
- **`run_scripts_thread` 巨型 if/elif 改为字典分发**：抽出 15 个 `_run_*` 方法与 `_run_script_dispatch`
  分发器，按脚本名查表调用；导入失败由分发器统一捕获返回 False。逻辑与重构前一致（成功→完成、
  导入失败→失败、运行期异常→错误、未实现→失败）。约 190 行分支缩减为查表，更易维护。
- **`send_coord` 等待循环增加 `check_stop()`**：AHK 迟迟未消费上一条坐标时，原本最长阻塞 1s 且无法中断，
  现允许 F9 在等待期间立即中断。

#### 代码质量机械整改（ruff 0.16.2）
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

#### 架构去重与工程化（本轮）
- 英雄识别去重：抽出 `warehouse._match_best_hero(face_roi, scale_min, scale_max, scale_step)`，统一三处
  `_recognize_hero` / `_best_multiscale_match_score` / `_iter_scales`（仓库扫描用 `HERO_TEMPLATE_SCALE_*`、
  阵容识别用 `LINEUP_HERO_TEMPLATE_SCALE_*`），匹配算法单源、行为完全不变，消除仓库扫描与阵容识别分叉隐患。
- 截屏缓存下沉：缓存逻辑内置进 `screenshot_bgr`（短 TTL 0.05s，每次仍 `check_stop` 保证 F9 即时中断），
  `wait_and_click` 点击后 `invalidate_screenshot_cache()` 使下一帧为最新；长任务重复截屏开销降低。
- `goldenhandmaidens.spec` 的 `hiddenimports` 改为 `glob` 自动收集顶层模块，新增 flow 脚本无需手改。
- 测试基线：新增 `tests/test_smoke.py`（pytest），覆盖全模块导入 + `_is_lineup_acceptable` 判定（2 passed）。
- 修复 `flow_migong` lambda 延迟绑定循环变量隐患（B023）。

#### 工程化（第二批）
- 点击辅助统一到 `common`：`click_and_wait`（冷却双检跳转）与通用 `click_template` 抽到 `common`；
  `flow_migong.click_mg` 保留为薄包装（migong 模板命名 / `cfg` 阈值解析后调 `common.click_template`），消除各脚本重复包装 `wait_and_click`。
- 阵容可采纳判定去重：`push` / `flow_tower` 两份相同 `_is_lineup_acceptable` 收敛为 `common.is_lineup_acceptable`
  （参数化 `level_score` / `special_hero_set`），两模块保留 1 行包装注入各自常量（push 含 `meimo`、flow_tower 为空），行为不变。
- 巨型主文件拆分：`Goldenhandmaidens.py` 顶层独立工具（stdout 接管 / 配置 / `ScriptConfig` / 快捷方式 / 窗口聚焦）抽到 `bot_runtime.py`，
  主文件由约 1637 行降至约 1443 行；原引用经 `from bot_runtime import (...)` 不变，无行为变化；`bot_runtime` 由 spec `glob` 自动收集。
- 坐标 IPC 维持文件通道（不做内存级改造）：AHK 端 `click_from_file.exe` 为编译产物、无 `.ahk` 源码，`send_coord` 写 `shared\target_coord.txt`、AHK 读取点击不变；
  尾部无条件 `time.sleep(0.5)` 改为「写后等 AHK 读走（文件被删除）再返回」，命中即返回更快且保证点击已发生，AHK 未运行退化为 0.5s 超时，行为不变。
- 验证：pytest 2 passed（全模块导入 + `_is_lineup_acceptable` 判定）；ruff F/B/SIM/UP/C4 全绿；`goldenhandmaidens.exe` 用 `runw.exe` 窗口引导器重建。

#### 修复：Lint（basedpyright 严格模式噪音）
- 新增 `pyrightconfig.json`，将 `typeCheckingMode` 设为 `basic`，消除项目（无类型标注的 tkinter 代码）
  中 `reportUninitializedInstanceVariable` / `reportUnknown*` / `reportUnannotatedClassAttribute` 等
  风格级噪音（原 Goldenhandmaidens.py 有 46 error + 645 warning）。
- 修复 `Goldenhandmaidens.py` 中 6 处真实可选类型报错：`_StdoutTee._orig` 的 `None` 成员访问、
  `ScriptConfig.last_run_time` 标注为 `str | None`、`show_log_window` 与 `_schedule_loop` 增加对
  `log_text` / `scheduled_time` 为 `None` 的守卫。修复后该文件 0 诊断。

### 上游合并与文档同步

#### 合并上游 v1.4.7（yangyh02/afk-journey-merlin-auto @ 6c7bbb8）
- `push.py`：礼包遮挡检测改为「连续 3 轮未命中候选模板」才触发（避免单轮误判）；`_st_on_end` 成功推进后重置 `lineup_start=0`（下一轮从第一套阵容开始）；新增 `_click_next_lineup`（连续 3 次短等待识别 right，全部失败才判定阵容用完）。
- `Goldenhandmaidens.py`：新增**本地持久化日志文件** `game_bot.log`（早期 `_PersistentStdout` + 运行期 `_StdoutTee` 双写文件 + `log()` 写文件；日志窗口新增「刷新 / 清空文件」按钮；文件写入失败时弹窗提示移到可写目录）；**循环推图**失败/异常由 `break` 改为 `continue`（与上游一致，单模式结束/失败不视为循环失败），并保留本仓「30 秒快速轮次」防空转安全阀（连续 3 轮 <30s 才停止）。
- `hero_metadata.py` / `warehouse.py`：新增英雄 `aidejia` / `sainie` / `xing` 元数据与种族/职业/中文名。
- `templates/`：新增 `aidejia.png` / `aidejia2.png` / `sainie.png` / `xing.png` 四张模板。
- `version.py`：升至 `v1.4.7`。
- 冲突解决：上游 v1.4.7 把本仓已拆到 `bot_runtime.py` 的顶层函数（`get_work_path` / `CONFIG_FILE` / `load_config` 等）连同新增日志设施整段加回 `Goldenhandmaidens.py`；本仓保留 `bot_runtime` 拆分，并将新增的日志设施（`LOG_FILE` / `_PersistentStdout` / `append_log_file` / 文件写入失败回调）落地到 `bot_runtime.py`，避免重复替换 `sys.stdout` 造成 stdout 接管冲突。

#### 文档同步（neat-freak 收尾）
- README「日志机制」描述修正：`_panel_log` 已不存在，改为 `_StdoutTee`（`bot_runtime`）+ 队列 `_enqueue_log` / `_drain_log_queue` 调度到主线程写面板，并经 `append_log_file` 持久化到 `game_bot.log`；`log()` 同样写面板并落盘。
- README「循环推图」行为修正：v1.4.7 合并后单个模式失败 / 异常**不停止**（自动切换到另一模式继续下一轮），仅连续 3 轮在 30 秒内异常结束或 F9 才停止——与代码一致。
- README「巨型主文件拆分」行数声明同步为「约 1568 行」（合并 v1.4.7 后 `Goldenhandmaidens.py` 由约 1483 行增至约 1568 行）。

#### 文档同步（neat-freak 收尾）
- README「项目结构」补齐实际模块：`push.py`（主线推图流程，原缺失）、`bot_runtime.py`（主文件拆分抽出的独立工具，原缺失）、`pata.py`（爬塔入口，被「爬塔」任务分发且内部调用 `flow_tower`，原缺失）；`flow_push.py` 标注由「推图流程」修正为「幻灵推图流程（薄封装）」，`flow_tower.py` 修正为「爬塔内部流程模块（被 pata.py 调用）」，与运行分发（`_run_pata`→`pata.main()`→`flow_tower.flow_tower()`）一致。
- README「项目结构」进一步补齐其余任务脚本（`youjian.py` 邮件、`pujing.py` 普竞、`nvshenta.py` 女神塔、`shouquguajijiangli.py` 挂机奖励、`shangcheng.py` 商城、`meirirenwulingqu.py` 日常任务）与工具（`youyishangcheng.py` 友谊商城、被商城调用；`jiance.py` 礼包/弹窗检测、被多任务复用），现已覆盖全部根目录任务 / 流程脚本。
- README「快速开始」补充推图 / 幻灵推图 / 循环推图 三者关系（源自 `run_scripts_thread` 运行分发代码）。
- README「巨型主文件拆分」行数声明同步为「约 1443 行（经后续增强，当前约 1483 行）」，与 `Goldenhandmaidens.py` 现状一致。

#### 合并上游 v1.4.6（merge e4adc3d）
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

### 审计改进第二批（B2 / B5 / B6 / B8–B11）

> 依据 [doc/AUDIT-REPORT-2026-11-04.md](doc/AUDIT-REPORT-2026-11-04.md)，由多个并行子 Agent
> 按文件边界分组执行。收尾门禁：`pytest -q` **126 passed**、`ruff check .` **64 条 = 存量基线**、
> `pwsh -NoProfile -File build.ps1 check` 退出码 0。

#### B2 区域变化检测单源化（`common.region_changed_since` / `common.crops_differ`）
- 新增两个原语：`crops_differ(before, after, threshold)` 只做自匹配比较（形状不一致返回 False，沿
  `hongbaolingqu._row_changed` 的既有语义）；`region_changed_since(before_crop, region, *, threshold,
  timeout, interval)` 在客户区相对区域上轮询取**新帧**（不用缓存帧）、循环内 `check_stop()`、`timeout=0`
  也先确认一次。
- 三个调用点改为复用：`fanfanle._wait_keys_change`、`yingxiongtingtang._wait_level_change`、
  `hongbaolingqu._row_changed`。**区域与阈值常量仍留在各调用方**（各界面噪声底不同）。
- 行为差异：旧实现把 `before` 小图在**整屏**里找最优匹配，新实现只在**同一客户区区域**内比较；语义更准，
  但非逐字节等价。新增 `tests/test_common_region_change.py` 9 条（同帧不变、平移 1px 必变、超时、
  `timeout=0` 单次确认、客户区原点、阈值边界、形状不一致、F9 透传）。
- 负验证：把比较方向写反 → 3 条用例变红；已精确还原。

#### B6 HUD 固定点位入口收敛（`common.tap_hud_entry`）
- 新增 `tap_hud_entry(client_pos, confirm, *, retries, click, log_func, precheck)`：收敛「客户区原点换算 →
  每轮尝试 → confirm 校验 → 失败日志」。`click` 由调用方注入，保留各自**已验证**的点击节奏：
  `hongbaolingqu` 的「目标」入口 `click_position(twice=True)`、`_tap_into_panel` `twice=False` 且
  precheck「已不在主界面即成功」、`haoyoujiangli` 的 `send_coord` 两次 + 0.4s/2.0s。
- 测试：`test_hongbaolingqu.py` / `test_haoyoujiangli.py` 各追加 1 条「confirm 恒假 → 重试用尽返回 False、
  点击数 = retries×2、坐标不漂移」；旧断言未改。负验证：把重试改成一次即返回 → 3 条变红。

#### B5 日志出口彻底统一
- `log_format.format_multiline()`：多行文本逐行 `format_body`、丢空行。
- `Goldenhandmaidens.run_scripts_thread` 的异常堆栈改为逐行带 `[HH:MM:SS]` 落盘（面板仍只首行）。
- `bot_runtime` 抽出 `_LineBuffer`，`_StdoutTee` 与 `_PersistentStdout` 共用；`_PersistentStdout` 控制台仍
  即时写原文，文件侧凑齐一行才格式化落盘，`flush()` 落残余且不重复。
- B10②：`log_format._task` 补「单运行循环假设」注释；`run_scripts_thread` 在任何 `set_task` 之前断言
  `current_task() is None`。
- 测试：`test_log_format.py` +6、`test_log_sink_persist.py` +1。负验证：整段堆栈当一行、`_PersistentStdout`
  退回原文直写 → 分别变红。

#### B11 多实例检测向量化（`flow_migong.find_all_instances_mg`）
- 双层纯 Python 像素循环改为 `np.argwhere(res >= threshold)` 后按**行主序**贪婪邻域抑制（与旧实现逐点等价；
  未采用审计原文的「按分数降序」，那会改变输出），末尾仍按 y 升序排序。
- 测试：新增等价性用例（测试内保留旧双层实现作参考，多峰/阈值边界/`dx == min_gap` 覆盖）与耗时门槛
  （20×24 res、50 次均值 < 1 ms，且对参考实现至少 2× 加速）。本机实测旧 0.053–0.085 ms → 新 0.010–0.024 ms。
- 负验证：换回双层循环 → 2× 加速断言失败（审计预估的「旧实现 1–3 ms」在本尺寸不成立，已在测试注释写明）。

#### B8 统一构建入口 + B9 lint 基线文件
- 新增 `build.ps1`（`build` / `check` / `clean`）与 `.ruff_baseline`（12 个文件、合计 64 条）。
  `check` = compileall（跳过 build/dist）→ pytest → ruff 按文件比对基线；ruff 未安装/无输出也会失败。
  `clean` 只删 `build`、`dist`、`__pycache__`、`.pytest_cache`、`.ruff_cache`，**不碰根目录成品 exe 与 templates/**。
- `.gitignore` 删除 `*.txt` 与 `!requirements*.txt`（否则未来任何 `.txt` 数据文件被静默忽略），新增两个缓存目录。
- `CLAUDE.md` 新增「项目专属门禁」；`doc/LIVE-DEBUGGING.md` §7/§8 改为引用 `build.ps1` 与 `.ruff_baseline`；
  README 二次开发与项目结构同步。
- 验证：`build.ps1 check` 退出码 0；故意新增未使用变量 → 失败并指名文件（探针已删）。

#### B10 整洁性收尾
- 经用户确认删除仓库根 `_tmp_click_srv.py`（长按假设已被实测推翻，现役点击器仍是 `click_from_file.exe`）。
- `tests/conftest.py`：无图形环境时先 `warnings.warn(PytestWarning)` 再 skip，跳过不再无声。
- README 补「`flow_*` 与非 `flow_*` 模块分工」命名说明；当前行数与「仓库管理」条目此前已补。
- 未做：拼音/英文模块批量重命名（收益低、风险高，按审计建议不做）。

#### B7 CHANGELOG 结构整理（未升版本）
- 按用户决定只整理结构：`## 未发布（Working）` 下按主题分 6 组、原 41 个 `###` 小节降为 `####` 归组，
  顶部加索引。正文行多重集与整理前**完全一致**（302 行逐字保留）。
- **仍待办**：`version.py` 仍为 `v1.4.7`，未切版本段、未打 tag；发版锚点需单独决策后执行。

#### B4 任务注册单源化评估（本轮未改代码）
- 结论：可做第一阶段（`ScriptConfig` 增加 `runner`，dispatch 由 `self.scripts` 派生），预计产品代码
  +25/−65 行、测试 +40 行；10 个无参任务可写 `"模块:函数"`，11 个保留 `_run_*` 包装（分别因为
  `auto_configure_lineup` / params 透传 / `push_settings` / 迷宫参数映射 / 仓库管理 / 登录特殊）。
- 不建议做第二阶段（`param_spec` 自动生成面板）：7 个面板含英雄网格、阵容下拉、单选与复选，tuple 无法表达。
- 加一个**无参**功能最少只改 1 处（追加一条 `ScriptConfig`）；带参功能仍需新增 `create_*_params` 分支，
  不是完全单源。`game_bot_config.json` schema 不变。本轮按用户决定只登记评估，不改代码。

### 性能优化第一批（2026-11-05）

> 由 3 个只读分析 Agent 用合成 1600×900 帧 + 真实模板测出热点，再由 5 个执行 Agent 按文件边界
> 并行落地。收尾门禁：`pytest -q` **163 passed**、`ruff check .` **64 条 = 存量基线**、
> `pwsh -NoProfile -File build.ps1 check` 退出码 0。

#### P0-1 模板内存缓存（`common.load_template`）
- `OrderedDict + Lock` 的 LRU（上限 64），key = `(abspath, mtime_ns, size)`；命中 `move_to_end`，
  `cv2.imread` 在锁外；失败结果不入缓存；APPDATA 副本重建后靠 mtime/size 自然失效。
- 实测（459 文件/5.08MB 模板目录）：命中 **0.0117ms**；未命中中位 **0.616ms**（均值 4.93ms 含大图冷读）。
  高频轮询里每个模板省 0.15–0.6ms；仓库/阵容这类上千次匹配的场景收益最大（本轮不启用仓库优化，
  但缓存本身是通用层）。
- 测试 6 条：命中只解码一次、mtime/size 变化失效、LRU 淘汰、失败不缓存、缺文件跳过缓存。

#### P0-2 `find_center_silent` 未命中路径
- 刷新窗口矩形后只有**矩形确实变化**才重新匹配；超时判断前置，`sleep(min(interval, remaining))`。
- 原来每次未命中固定 2 次 `matchTemplate` + 2 次截图；现在 1 次。按全帧 61–130ms 计，
  每次未命中省 60–130ms；`push` 的短超时轮询与 `timeout=0.25/interval=0.5` 不再睡过 deadline。
- 测试 5 条（矩形不变/变化、sleep 截断、显式 region 不刷新、命中坐标不变），
  负验证：恢复无条件 `continue` → 单次匹配用例变红。

#### P0-3 模板校验快速指纹（frozen 启动）
- `_templates_fast_marker` = 排序后 `相对路径:size:首4KB摘要:尾4KB摘要` 的整体 sha256；
  `%APPDATA%\gamebot\templates.marker` 存「内置 + APPDATA」两行指纹。命中直接用 APPDATA，
  只有不一致才回落到全量 sha256 深度校验/重拷贝。
- 实测 459 文件：快速指纹 **32–40ms**（首读 188ms），全量深度 **337ms**（暖缓存），
  原 frozen 启动两遍校验约 **0.8–1.1s** → 快速路径约几十 ms。
- 残余风险已写进注释：APPDATA 中「大小不变且首尾 4KB 不变」的位级损坏不会被快速路径发现，
  需删 `templates.marker` 触发深度校验。测试 7 条（首次复制、二次快速路径不深度校验、
  删文件/同大小改内容触发重拷贝、marker 缺失/损坏回退、开发模式不碰 APPDATA）。

#### P1-1 客户区相对搜索区域 + 底部带推广
- `find_center` / `find_center_silent` / `wait_and_click` / `click_template` 新增 `client_region`
  （客户区相对，内部按 `game_client_region()` 换算；与整屏绝对的 `region` 互斥）；
  `find_center_silent` 传 `client_region` 时每轮重算原点且跳过强制刷新分支。
- 新增 `common.BOTTOM_BAR_CLIENT_REGION = (0, 650, 1600, 250)`，只推广到**位置确定**的
  底部导航/底部页签：`at_main_interface` 的 wanfamulu、push/pujing/nvshenta/mimengzhiyu/
  pata/flow_gonghui/shouquguajijiangli 的 wanfamulu 点击、hongbaolingqu 的 `_panel_open`
  与全部底部页签。返回箭头（exitck/fanhui）、战斗/结算页、弹窗、标题/中部宝箱/右侧 HUD
  保持全客户区。
- 实测 wanfamulu（65×19，1600×900 合成帧）：全客户区 **61.21ms** → 底部带 **18.08ms**（**3.38×**）。
- 测试 12 条：换算/互斥/无窗口回退、坐标补偿、区域外不命中、窗口移动重算、透传、
  旧调用不变、返回箭头底带外守卫。负验证：去掉原点换算 → 3 条红；给返回箭头加底带 → 守卫红。

#### P1-2 红点领取轮询收敛（`hongbaolingqu`）
- `_panel_open` 改「每轮同帧检查 4 个页签（`timeout=0`）+ 0.3s 外层轮询 + 2.0s 总窗口」，
  面板未打开时由最坏约 5.4s 收敛到 ≤2.0s；已打开时首轮即返回。
- `claim_current_view` 首轮保留 1.0s 宽限，后续轮次一键领取 `timeout=0`（单个「领取」仍保留
  0.5s 动画宽限）。按 25 个视图、每个视图多次单项领取估算，单轮约省 35s（估算值，待实跑复核）。
- 新增 4 条用例；负验证：改回逐个 1s 顺序检查 → 3 条红；首轮宽限改成永远 1.0 → 1 条红。

#### P2-1 GUI 全局热键延后注册
- `GameBotGUI.__init__` 里的 `_register_hotkeys()` 改为 `root.after(200, ...)`，并把
  `_hk_start/_hk_stop` 预置为 None；代价是启动后约 0.2s 内 F8/F9 不可用。
- 实测 GUI 构造：立即注册 423/389ms → 延迟注册 **242/248ms**（省 **140–175ms**）；
  含 Tk 建窗总耗时 792/796ms → 671/694ms。
- 新增 1 条用例（构造期零调用、`update()` 后恰好一次、测试不装真实全局热键）。

#### P2-2 `updater` 延迟导入
- 顶层 `import updater` 删除，改为四个更新路径（自动检查/手动检查/下载/安装重启）各自局部 import。
- 实测从启动导入中移除约 **15.6ms**（urllib.request 14.1ms + ssl 2.7ms）。
- 新增 2 条用例：子进程断言 `updater` 不在 `sys.modules`（并把日志重定向到 tmp）、
  AST 守卫顶层无 import 且四个路径都有局部 import。

#### 已评估后放弃
- **WGC 回调 `cv2.cvtColor(COLOR_BGRA2BGR)`**：代码在取帧后已经调用
  `frame.convert_to_bgr()`，`frame_buffer` 已是 3 通道 BGR；再加 cvtColor 属于重复转换，
  没有收益。保留 `np.array(..., copy=True)`（必须脱离复用缓冲）。
- **OpenCV 发行版/onedir/UPX/`optimize` 等打包形态变更**：收益 0.5–1.5s，但会改变交付形态、
  需全量回归，且本机未装 UPX，按「不为凑数硬上」放弃。
- **灰度匹配、压缩 `random_sleep`、缩短战斗轮询/超时**：会改变判定语义或防检测节奏，不碰。

#### 暂不做（用户明确）
- **迷宫（`flow_migong`）**：`find_all_mg_fast` 半分辨率粗筛等。
- **仓库（`warehouse`）**：`DEBUG_SAVE_SLOTS` 默认关闭、42 组合固定等待改造等。
- 以上两项因用户平时不用，整体标记「暂不处理」，不为它们花时间。

### 日常流程修复、GUI 状态与失败现场留存（2026-11-05 第二批）

> 依据今日 `game_bot.log` 与用户实机反馈修复。收尾门禁：`pytest -q` **212 passed**、
> `ruff check .` **64 条 = 存量基线**、`build.ps1 check` 退出码 0。

#### GUI：未勾选不再「排队」、旧状态不再残留
- 根因：`_begin_run` 把全部脚本置 `等待中`，`run_scripts_thread` 又跳过未勾选项，跳过的行永远停在「排队」；
  上次的 `失败/错误` 也会一直留着。
- 新增 `_prepare_run_statuses()`：先把全部脚本回「就绪」，只把本轮实际会执行的置「等待中」；
  「只运行当前功能」只置传入的那一个。`stop_all` 把 `等待中` 收回「就绪」，运行循环提前结束时同样清理。
- 今日 log 的 `row2 邮件 check=False text=失败`、`row5 迷梦 check=True text=排队` 即此问题，已消除。

#### GUI：「开始运行」与「立即开始」语义分开
- `开始运行 (F8)` = 只按勾选顺序运行脚本，不碰游戏窗口/启动器。
- `立即开始` = 游戏**未运行**才按快捷方式启动并等待配置秒数；已在运行则跳过启动、0 延迟直接跑脚本。
  避免用户重复拉起客户端/启动器。

#### 失败/超时现场逐帧留存
- `common.screenshot_bgr()` 维护最近 **5 帧**的环形缓冲（只存引用，不复制大图）。
- 任务返回失败/超时或抛异常时，`capture_failure_context()` 在 `debug/failures/<时间>_<任务>/`
  写 `frame_00.jpg…`（JPEG 80）、`client.jpg` 与 `meta.txt`（任务/原因/时间/客户区/帧时间戳）；
  只保留最近 5 个现场。F9 主动停止不落盘。
- 兼容中文任务名：`cv2.imwrite` 在非 ASCII 路径会静默失败，改用 `imencode + 二进制写`。

#### 红点领取：8 个子项开关
- GUI 配置面板新增 8 个勾选框：每日任务 / 公会任务 / 成长挑战 / 赛季任务 / 家园目标 /
  赛季手册 / 月桂之旅 / 赛季挂机关卡；默认全开，改动立即写回 `script.params`。
- 运行时 `hongbaolingqu.main(params=...)` 按 `claim_daily/guild/growth/season/homestead/
  season_book/laurel/idle` 逐项跳过；8 项全关视为「无活可干」，返回成功而不是失败。
- 今日 log 中 `赛季任务 领取 0 项` 且完全没有二级页记录：`tpl_wanfa` 锚点未命中导致上方
  玩法/活跃/限时/养成/剧情 5 个页签整段跳过。增加固定点位兜底 `(531,248)+[0,132,264,397,532]`
  （客户区相对，实机截图校准），命中锚点仍走原逻辑。
- 领取日志降噪：首轮一键领取保留 1s 宽限；后续轮次改静默匹配 + 单点，不再每轮打印
  `放弃 yijianlingqu`（今日 log 里这类行刷了几十行）。

#### 好友面板额外奖励
- `haoyoujiangli` 在一键赠礼并收取之后，再扫描 `lingqu` / `baoxiang_full`（最多 5 次），
  命中后点击、清理弹窗；宝箱弹出的 `shouhuojiangli` 也补点。覆盖右侧好友按钮里的剩余奖励。

#### 女神塔：登顶后回退再扫荡
- 今日 log：`nvshentaxiayiceng` 10s 未出现 → 退出；随后 `nvshentasaodang` 15s 未出现 → 扫荡失败。
- 新增 `_back_to_tower_page()`：先查扫荡按钮，否则逐层 `exit` / `exitck` 退出并复查，最多 3 轮；
  回到女神塔页面后再走原 `do_saodang_and_exit()`。

#### 邮件 / 爬塔
- 邮件：点击 `youjian` 后改为轮询 `yueduquanbu` / `notyueduquanbu` 最多 5s，避免面板加载慢时
  单次判定误判失败（今日 log 中 `youjian` 连续 19 次未命中、6.6s 才出现）。
- 爬塔：`flow_pata` 开头先 `recover_to_main_interface()`，避免从上一任务的子页面开始时，
  子页底部同名 wanfamulu 图标造成误判，随后找不到 `pata`（今日 log 20.1s 失败）。

#### 家园愿望单：不再误点制作配方
- 生产界面里 `tpl_wish_label` 只用于确认已进入，**删除**其下方「选择」产品卡片的点击
  （该点击会打开制作配方）；直接固定点两次数量档（x10）后点开始。删除不再使用的
  `WISH_SELECT_OFFSET_Y`；标签仍存在时补 0.3s 轮询间隔，避免空转。

#### 英雄厅堂 / 迷梦之域补领
- 英雄厅堂：进厅堂后先扫**中央附近** `(550,250,500,400)` 宝箱与**右上角** `(1200,0,400,300)`
  领取/一键领取；命中后点宝箱/领取，必要时点「收获奖励」。
- 迷梦之域：进界面后先扫右上角同类奖励；结算清理失败时增加 `recover_to_main_interface()`
  兜底并记录日志，不改变原成败语义。
- 两处只关闭确实存在的奖励弹窗（`dismiss_popup_away_from`），不使用会点空白的
  `dismiss_popup`，避免误触返回。

#### 今日 log 的其余发现（未改代码）
- 推图连续失败 10/10 后停止、结社战线本场失败：属账号练度/战斗结果，不是流程缺陷。
- 普竞 `mianfeimenpiao/fufeimenpiao` 3s 未出现、`tiaoguo` 15s 未出现：更像当天无票/界面状态，
  未改判定阈值，避免把「无票」误判成流程错误。
- 迷梦 93.3s 失败已加退出兜底；邮件 28.2s 偏慢已加面板轮询，仍需实跑复核。

### 实机逐项复测与三处入口修正（2026-11-05 第三批）

> 依据上一提交的修复项逐项在真实客户端复测（客户区 1600×900、游戏进程提权、点击经
> `shared/target_coord.txt` 交给提权 `click_from_file.exe`）。收尾门禁：`build.ps1 check`
> 通过（pytest 212 passed、ruff 64 条与基线一致）。

#### 爬塔入口：卡片名被底部页签栏遮挡，模板永远等不到
- **实测**：玩法目录里「天穹试炼」卡在第三行，卡名被底部页签栏压住，`pata.png` 文本模板
  匹配不到，`wait_and_click` 满 15 秒超时后直接放弃。
- **修正**：3 秒内未命中则按客户区固定点 `PATA_CARD_POS=(625,700)` 点卡片可见区，
  再用 `_pata_panel_open()` 确认——任一塔的「出发」按钮出现即判定已进入选择界面；
  确认失败才判失败，不再「点了就当进去了」。
- **复测**：日志出现「「天穹试炼」卡名被页签栏遮挡，已按固定卡片点位进入。」，随后识别到
  不朽之塔的「出发!」（其余塔提示「不在开放时间内」），确认已停在塔选择界面。

#### 红点领取：每日任务页签改用固定点位，赛季任务先切「赛季阶段」
- `richangrenwutab.png` 与底栏其它图标文字灰度相近，实测会误匹配到「赛季任务」页签。
  改为客户区固定点 `TASK_HUD_DAILY_POS=(687,850)`（点完不依赖模板自证），删除该模板
  并从 `PANEL_TAB_TEMPLATES` 中移除。
- 顶部 5 个分类页签**只在底部「赛季阶段」子页出现**，面板会记住上次停留的子页（实测常停在
  「赛季成长任务」）。`_sweep_season_task_tab` 先点 `tpl_saijijieduan` 切回「赛季阶段」；
  连选中态模板也匹配不到时按固定点 `SEASON_STAGE_SUB_TAB_POS=(1152,795)` 补切一次。
  固定栅格基准同步校准为 `SEASON_SUB_TAB_FALLBACK_ORIGIN=(531,248)`。
- **复测**：全开关跑完仅「赛季任务 领取 1 项」；只开 `claim_season`、其余 7 项关闭时，
  日志逐项打印「（已关闭，跳过）」，未误触其它页面。

#### 月桂之旅：右侧 HUD 没有直达入口，改走菜单卡片
- **实测**：点主界面右侧竖排 `(1550,610)` 只会落回主界面，没有月桂之旅面板。
  真入口在「菜单」第二行第 4 张卡片，客户区中心 `LAUREL_MENU_POS=(905,625)`。
- 新增 `_open_laurel_journey()`：开菜单 → 点卡片 → 用菜单内「任务」卡片是否消失确认进入，
  最多重试 2 次；日志与子页扫描逻辑不变。
- **复测**：从菜单进入、逐本记扫描、赛季手册与当前进度返回均正常，全程约 3 分钟结束，
  未复现此前 10:41 的弹窗阻塞。

#### 复测清单与结论
- **GUI 启动语义**：仅勾选「邮件」后点「立即开始」，日志出现
  「游戏已在运行，跳过启动，立即开始脚本」→ `▶ [1/1] 邮件` → `✔ [1/1] 邮件 · 13.6s`
  → 「所有脚本已停止」；界面仅邮件行显示绿色「完成」徽标，其余行无排队/运行残留。
- **邮件轮询**：识别 `notyueduquanbu` 后正常退出（7.2s）；第二次 13.6s。
- **好友奖励**：已赠礼跳过、额外奖励扫描 0 项，正常回主界面。
- **迷梦之域**：完成 1 次挑战、跳过战斗、结算清理后 exit 确认回主界面（41.8s）；
  右上角奖励「未发现可领奖励，跳过」（当日无可领）。
- **女神塔**：已通关态检测到「扫荡」→ 回祭标识 → 最大扫荡 → confirm → 点空白 → exit（25.4s）。
- **家园愿望单**：20 单交付、领取进度奖励 1 次、自动制作 0 次（216.9s）。
- **失败现场留存**：`debug/failures/` 落盘 3 帧连拍 + `client.jpg` + `meta.txt`。
- **环境未触发**：女神塔登顶回退（当日已通关）、愿望单缺料自动制作（当日无缺料）。
- **英雄厅堂右上角**：今日复测截图确认右上只有 图鉴 / 编队 / 异界雇佣 三个图标，均无红点、
  数字角标或领取入口；中央宝箱与右上角两组模板扫描均未命中。该项需用户指出具体入口，
  或在真有未领奖励时复测，暂不按猜测盲点。

#### 文档对齐（2026-11-05 洁癖收尾）
- README「红点领取」里的月桂之旅入口由「右侧 HUD (1550,610)」改为菜单卡片 (905,625)，
  与第三批复测结论一致；本文件旧条目同步补上更正说明，避免两处说法并存。
- README 公会玩法模板计数 17 → 18，补上漏列的 `jiesheshibai`（失败结算标题，用于提前结束挑战），
  与实际 `templates/` 下的 18 个文件一致。
- 清理未发布段中三处 `daily_reset=True` 表述（该字段已在 GUI 改造中整体移除），
  改为「启用状态由左侧勾选决定」。
- 核对结论：README 项目结构覆盖根目录全部 `.py`；`doc/` 现役规范为
  `TEMPLATE-AUTHORING.md` 与 `LIVE-DEBUGGING.md`，`AUDIT-REPORT-*.md` 已标明为历史快照；
  测试基线 212 条与 `pytest --collect-only` 实际收集数一致。

