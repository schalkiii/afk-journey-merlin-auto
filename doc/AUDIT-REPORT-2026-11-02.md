# 情况说明与改进建议（项目全面审计）

审计日期：2026-11-02
审计范围：`afk-journey-merlin-auto` 全部代码与文档（`main` 分支 @ `eb332ea`）
本文档**只描述事实与建议，不含任何已执行的改动**。每条建议都可直接交给执行 Agent 开工。

---

## 一、现状描述（可观察事实）

**规模**

| 项 | 实测值 |
|---|---|
| 顶层 Python 文件 | 33 个，共 9378 行 |
| 最大文件 | `Goldenhandmaidens.py` 1674 行 |
| 次大文件 | `warehouse.py` 919、`push.py` 870、`flow_migong.py` 849、`flow_tower.py` 815、`common.py` 708 |
| 模板资源 | `templates/*.png` 309 张 |
| 测试 | `tests/test_smoke.py` 1 个文件 34 行，2 个用例 |
| 本地日志 | `game_bot.log` 8,863,373 字节 |

**结构**

- 无包目录，全部模块平铺在仓库根；`common.py` 是唯一的共享底层（模板匹配、坐标 IPC、协作式停止、日志汇聚、界面恢复）。
- 任务脚本（`youjian.py` / `pata.py` / `nvshenta.py` / `yuanwangdan.py` / `jieshezhanxian.py` …）各自 `from common import ...`，由 `Goldenhandmaidens.py` 的 GUI 按名字分发调用。
- 点击链路：Python 写 `shared/target_coord.txt` → `click_from_file.exe`（AHK 编译产物，无源码入库）读取并注入点击。
- 感知链路：`pyautogui.screenshot()` 全屏截图 → OpenCV `TM_CCOEFF_NORMED` 模板匹配 → 返回全屏绝对坐标。项目**没有 OCR**。

**质量水平**

- 每个模块顶部有中文 docstring 说明流程与设计动机；注释普遍解释"为什么"，并记录了实测踩坑（如「一键选择必须再点一次交付」）。
- `ruff check .` 报 64 项（BLE001 31、S110 7、PLW1510 6、RUF046 5、DTZ005 4、RUF059 4、I001 3、PLW0602 2、RUF010 1、RUF013 1），全部位于既有代码，无 CI 门禁。
- 无 `doc/` 目录；文档为根目录 `README.md` + `CHANGELOG.md` + `CLAUDE.md`。

---

## 二、问题清单（按七个维度）

严重程度：**高**=会造成功能错误或静默丢失用户利益；**中**=维护陷阱/可用性受损；**低**=规范与整洁。

### 维度 1：文档一致性

| ID | 位置 | 问题 | 严重 | 影响 |
|---|---|---|---|---|
| D1-1 | `README.md:139` | 写「（经后续增强与合并上游，当前约 1568 行）」，实测 `Goldenhandmaidens.py` 为 **1674** 行 | 低 | 文档给出的规模数字不可信 |
| D1-2 | `README.md:167`（运行环境） | 声明「屏幕分辨率 1600×900，模板基于此分辨率采集」，但 `templates/` 内仍存在按 1302×1080 采集且**当前无代码引用**的模板（`zhizuox10.png`、`xinyuandanjiangli.png`），且没有任何机械校验能发现分辨率错配 | 中 | 换窗口尺寸会整功能静默失效（本轮 `yuanwangdan.py` 全功能失效即此因，实跑交付 0 单） |
| D1-3 | `common.py:1`、`flow_enter.py:1`、`meirirenwulingqu.py:1`、`shangcheng.py:1`、`shouquguajijiangli.py:1`、`start.py:1`、`youjian.py:1`、`youyishangcheng.py:1` | 首行残留 `# F:\afkj\game-bot\xxx.py` 绝对路径注释，指向本仓库不存在的路径 | 低 | 误导定位；读者以为文件在别处 |
| D1-4 | `README.md:275`（开发相关） | 写「已完成家园愿望单、公会玩法日常（结社战线 / 狩猎悬赏）。计划更新荣誉对决。」——但同文档第 1 节功能表未列出这两个新任务 | 低 | 功能总览与实际能力不一致 |

### 维度 2：文档缺漏

| ID | 位置 | 问题 | 严重 | 影响 |
|---|---|---|---|---|
| D2-1 | 全项目 | 无「新增一个任务脚本要改哪几处」的说明。实测需同步 3 处：`Goldenhandmaidens.py:1231-1300` 区间的 `_run_*` 方法、`scripts` 列表的 `ScriptConfig(...)`（18 处）、`_run_script_dispatch` 的分发字典（18 处） | 中 | 新增任务极易漏改（本轮就出现过代码入库而模板未入库） |
| D2-2 | 全项目 | 无**模板采集规范**：采集分辨率、裁切须避开角标/流光动画、阈值标定方法、命名约定（`玩法名 + 控件拼音`）都只散落在各模块 docstring 与 CHANGELOG 里 | 高 | 这是本轮 `yuanwangdan` 整功能失效、`kaishipengren` 裁错位置、`xinyuandanwancheng` 因动画抖动误判三个问题的共同根因 |
| D2-3 | `README.md:178` | 提权只写「以管理员身份运行 goldenhandmaidens.exe（点击注入需要管理员权限）」，未说明真实约束：游戏进程本身以管理员运行时，**非提权进程的点击会被 UIPI 静默丢弃**（不报错、不弹窗，表现为界面毫无反应） | 中 | 二次开发者与 Agent 会把"点击没生效"误判成界面逻辑问题 |

### 维度 3：架构优化点

| ID | 位置 | 问题 | 严重 | 影响 |
|---|---|---|---|---|
| D3-1 | `Goldenhandmaidens.py:1242-1302` | **任务结果语义不统一**：`_run_youjian` / `_run_haoyou` / `_run_pujing` / `_run_nvshenta` / `_run_guajijiangli` / `_run_shangcheng` / `_run_meiri` / `_run_pata` 全部调用后硬编码 `return True`；而 `youjian.py` / `haoyoujiangli.py` / `shouquguajijiangli.py` / `shangcheng.py` / `meirirenwulingqu.py` 的 `main()` **根本没有返回成败值**（实测 bool 返回语句数 = 0） | 高 | GUI 用返回值判定「完成/失败」，并在 `daily_reset` 脚本"成功"后**自动取消勾选**（`Goldenhandmaidens.py` 运行循环内 `if script.daily_reset: script.enabled = False`）。因此这 5 个每日任务**即使完全没做成也会被标记完成并取消勾选**，用户当天该任务被静默跳过，且日志显示「执行完成」 |
| D3-2 | `common.py:31` vs `:157` | 两套路径解析语义混用：`get_resource_path` 在打包后指向 `_MEIPASS`（只读、可能被杀软清理），`get_work_path` 指向 exe 同目录。但用户可编辑的 `migong_config.json`（`flow_migong.py:33`）、`formations.json`（`formation.py:25`、`Goldenhandmaidens.py:869`）、`grid_offsets.json`（`formation.py:50`）都经 `get_resource_path` 读取 | 中 | 打包后用户修改 exe 同目录的这些 JSON **不生效**；且 `common.py:65` 专门为模板建立了 APPDATA 副本来规避 `_MEIPASS` 被清理，配置 JSON 没有同样保护 |
| D3-3 | `start.py:16,66-69` | 用 `get_resource_path("templates")` 自行拼模板路径，绕过 `common.get_templates_dir()` 的 APPDATA 副本机制 | 中 | 恰好在"杀软清理 `_MEIPASS`"这一 `common` 设计要解决的场景下，登录任务会找不到模板而失败 |
| D3-4 | `flow_tower.py:31`、`mimengzhiyu.py:17`、`nvshenta.py:16`、`pata.py:8`、`pujing.py:9` | `random_sleep()` 在 5 个文件各自重复实现（同为 `time.sleep(random.uniform(2.0,3.0))`） | 低 | 改等待策略需改 5 处 |

### 维度 4：代码写法

| ID | 位置 | 问题 | 严重 | 影响 |
|---|---|---|---|---|
| D4-1 | `common.py:444` `send_coord` | 点击器（`click_from_file.exe`）未运行或已自行退出时，函数自旋等待 0.5 秒后**静默返回**，与"点击成功"完全不可区分 | 高 | 实测发生：`click_from_file.exe` 长时间运行后自行退出，此后所有点击空打，日志表现为「界面连续 N 轮无变化」，本轮据此把"厨房按钮无响应"误判成界面逻辑变化，浪费大量排查。项目自身 GUI 也只在启动时探测一次存活 |
| D4-2 | `common.py:314` `click_blank_to_exit`、`:327` `dismiss_popup` | 两者都点**屏幕底部居中**（`w//2, h*0.85`）或「点击空白处关闭」模板中心。实测该位置与多个面板主按钮重合：结社战线「扫荡」在其下方 15px 内、狩猎悬赏「搜寻精怪」2px 内、家园愿望单「交付/一键选择」63px 内 | 中 | `ensure_main_interface()` 在**每个任务开始前**调用 `dismiss_popup()`，可能误触发上一任务遗留界面上的主按钮（如误扫一次、误抽一次悬赏）。`common.py:490` 已有正确的 `dismiss_popup_away_from`，但这两个老函数未收敛到它 |
| D4-3 | `common.py:28-29` | `_ACTIVE_TEMPLATES_DIR = None` 连续重复两行 | 低 | 冗余 |
| D4-4 | 全项目 | 31 处 `BLE001`（裸捕 Exception）+ 7 处 `S110`（except 后 pass） | 中 | 异常被吞后无痕迹，排障时看不到根因 |
| D4-5 | `yuanwangdan.py:53,64`、`jieshezhanxian.py`、`lieshouxunshang.py` | 像素魔数分散在各模块（`GIFT_CLICK_OFFSET`、`QTY_BUTTON_OFFSET`、`POPUP_BLANK_OFFSET`、`GRID_REGION`），且各模块各写一份 | 中 | 分辨率一变需满仓库找常量重标定；无集中定义处，易漏改 |

### 维度 5：测试覆盖率

| ID | 位置 | 问题 | 严重 | 影响 |
|---|---|---|---|---|
| D5-1 | `tests/` | 仅 2 个用例。本轮新增的 `flow_gonghui.py` / `jieshezhanxian.py` / `lieshouxunshang.py` 与重写后的 `yuanwangdan.py` 状态机、GUI 拖拽排序/顺序持久化，**均无测试**。这些模块里有大量可纯逻辑测试的部分：区域矩形推算、阈值互斥判定、`_wait_gone` 语义、重排后选中项跟随、配置里缺新功能时的补位顺序 | 高 | 回归无保护。本轮 GUI 拖拽改动只能靠临时手写冒烟脚本验证（已验证通过，但脚本未入库） |

### 维度 6：测试严谨性

| ID | 位置 | 问题 | 严重 | 影响 |
|---|---|---|---|---|
| D6-1 | `tests/test_smoke.py:14-21` | `test_all_modules_import` 只断言"能 import 不抛异常"，不检查任何行为；且 `start.py` 被无条件排除在导入清单外，**没有注释说明原因** | 中 | 一个把所有模块 import 都写坏以外的问题都测不出来；排除项的原因不可追溯 |
| D6-2 | `tests/` | 无「代码引用的模板 ↔ `templates/` 实际文件」一致性检查，也无「模板采集分辨率」检查 | 高 | 上一轮 `yuanwangdan.py` **连代码带全部模板都没 `git add`**，测试依然全绿；clone 者直接 `ValueError: 模板读取失败` |

### 维度 7：工程规范

| ID | 位置 | 问题 | 严重 | 影响 |
|---|---|---|---|---|
| D7-1 | `bot_runtime.py:69` `append_log_file` | 纯追加写，无轮转/上限。实测 `game_bot.log` 已 8.86 MB | 中 | 长期无人值守运行会持续膨胀，且日志窗口读取变慢 |
| D7-2 | `version.py:1` | 仍为 `v1.4.7`，而 CHANGELOG 有整节未发布改动、exe 已重新编译（92 MB，11-02 10:06） | 中 | 用户与开发者都无法区分"装的 exe 是哪个版本"，`updater.py` 的对比也会失真 |
| D7-3 | 仓库根 | 32 个 `_tmp_*` 调试文件（约 20 MB，含截图/日志/临时脚本）仍在工作区；本轮已补 `.gitignore` 但文件未删 | 低 | 接手者看到一堆来历不明的根目录文件 |
| D7-4 | 全项目 | 无 CI；`ruff` 64 项基线告警无人认领，与用户全局规则「lint 清零或逐条登记 pending」不符 | 中 | 规范只存在于口头，无法阻止新增告警 |

**结论**：七个维度均已给出结论，无一维遗漏。

---

## 三、改进建议（逐条：做法 / 文件清单 / 验证方式）

### A1【高】统一任务成败语义，杜绝"失败也算完成"（对应 D3-1）

**做法**
1. 给 `youjian.main` / `haoyoujiangli.main` / `shouquguajijiangli.main` / `shangcheng.main` / `meirirenwulingqu.main` 增加明确返回值：流程关键步骤任一失败即 `return False`，全部走完 `return True`（参照 `yuanwangdan.main` 的写法）。
2. `Goldenhandmaidens.py` 的 8 个 `_run_*` 改为 `return <flow>(...)`，删除硬编码 `return True`。
3. 对确实无法判定成败的历史流程，宁可返回 `False` 并在日志写明「无法确认结果，不自动关闭勾选」，也不要返回 `True`。

**文件**：`youjian.py`、`haoyoujiangli.py`、`shouquguajijiangli.py`、`shangcheng.py`、`meirirenwulingqu.py`、`pata.py`、`pujing.py`、`nvshenta.py`、`Goldenhandmaidens.py:1242-1302`

**验证**：新增单测——monkeypatch 让流程函数返回 `False`，断言 `_run_script_dispatch` 返回 `False` 且运行循环**不**把该 `daily_reset` 脚本置为 `enabled=False`；返回 `True` 时才取消勾选。

### A2【高】点击器存活探测，点击不再静默失败（对应 D4-1）

**做法**
1. 在 `common.py` 增加 `clicker_alive()`：写入哨兵坐标并轮询文件是否被消费（本轮已在 `_devshots/explore.py` 实测可用，可直接产品化）。
2. `send_coord` 在"写后超时未被消费"时累计计数，连续 N 次（建议 3）未消费即 `log("点击注入未生效：click_from_file.exe 可能已退出")` 并抛出可被 GUI 捕获的异常（或置一个 `clicker_lost` 标志）。
3. `Goldenhandmaidens.run_scripts_thread` 在每个任务开始前调用一次 `clicker_alive()`，失败则尝试重新拉起 `click_from_file.exe`（提权场景无法自动拉起时明确报错停止），不要继续空跑。

**文件**：`common.py:444`（`send_coord` 附近）、`Goldenhandmaidens.py`（`run_scripts_thread` 任务循环）

**验证**：单测——把 `coord_path` 指向一个不会被删除的临时文件，断言 `clicker_alive()` 返回 `False`、且连续 3 次 `send_coord` 后触发告警；正常情况（消费）不告警。

### A3【高】补模板采集规范 + 机械校验（对应 D2-2、D1-2、D6-2）

**做法**
1. 新建 `doc/TEMPLATE-AUTHORING.md`（或根目录 `TEMPLATES.md`）：写清①一律在 1600×900 客户区采集；②裁切须避开角标（完成/新/档位角标）与带流光动画的标题，动画标题实测匹配分会在 0.82–0.95 抖动，须另找静态锚点或加兜底判定；③命名 = 玩法名 + 控件拼音；④阈值标定方法（记录目标自身匹配分与"最易混淆界面"的最高分，两者留 ≥0.1 余量）。
2. 新增 `tests/test_templates.py`：
   - 用正则收集全项目 `get_template_path("X.png")` 的字面量引用，断言每个引用在 `templates/` 下存在（防"代码入库、模板漏入库"）。
   - 断言每张**被引用**的 PNG 宽高比与 1600×900 客户区采集一致（可用"模板尺寸 ≤ 客户区且非 0"这一弱断言起步），并对孤立文件（无引用）输出清单告警。

**文件**：新建 `doc/TEMPLATE-AUTHORING.md`、`tests/test_templates.py`

**验证**：故意删一张被引用的模板 → 测试必须失败；把某模板改名 → 测试必须失败。

### A4【中】任务注册单源化（对应 D3-1 附带、D2-1）

**做法**：把「功能名 → 执行函数」收敛成一张表（模块级 `TASK_REGISTRY: list[tuple[名称, 默认启用, daily_reset, 参数, 执行函数]]`），`scripts` 列表与 `_run_script_dispatch` 都由它生成；`_run_*` 方法保留为薄包装或直接引用函数对象。同时在 README 增加「新增任务只需改这一处 + 写一个 main() 返回 bool」的说明。

**文件**：`Goldenhandmaidens.py`（`scripts` 初始化、`_run_*` 区、`_run_script_dispatch`）、`README.md`

**验证**：注册表长度 == `ScriptConfig` 数量 == 分发表长度（写成断言单测）；新增一个假任务只改注册表即可在 GUI 出现并可运行。

### A5【中】统一弹窗关闭，消除底部热区误触（对应 D4-2）

**做法**：让 `dismiss_popup()` 复用 `dismiss_popup_away_from()`（点「点击空白处关闭」文字左上方空白处），仅在其不存在时回退到 `click_blank_to_exit()`；同时把 `click_blank_to_exit()` 的兜底点从底部居中改为**左下 1/4 处**（避开底栏与面板主按钮）。

**文件**：`common.py:314`、`:327`、`:380`（`ensure_main_interface` 调用链）

**验证**：单测 monkeypatch `find_center_silent`，断言 `dismiss_popup()` 实际点击坐标相对「点击空白处关闭」中心有 (-400,-200) 级偏移，而非落在中心。

### A6【中】配置与模板路径语义统一（对应 D3-2、D3-3）

**做法**：①`start.py` 改用 `common.get_template_path(...)`；②用户可编辑 JSON（`migong_config.json` / `formations.json` / `grid_offsets.json`）读取改为"先 `get_work_path`（exe 同目录，用户可改），不存在再回退 `get_resource_path`（打包内置）"；③在 `common.py` 用注释写明两个 helper 的适用边界（内置只读资源 vs 用户可编辑/持久化文件）。

**文件**：`start.py:16,66-69`、`flow_migong.py:33`、`formation.py:25,50`、`Goldenhandmaidens.py:869`、`common.py:31,157`

**验证**：单测——在临时工作目录放一份内容不同的 `formations.json`，断言打包路径分支下读到的是工作目录那份。

### A7【中】日志轮转（对应 D7-1）

**做法**：`append_log_file` 改为写入前检查大小，超过阈值（建议 5 MB）就把 `game_bot.log` 改名为 `game_bot.log.1`（滚动保留 1–2 份）再新建；或直接用 `logging.handlers.RotatingFileHandler`。GUI 的「清空日志」按钮语义保持"清空当前文件"。

**文件**：`bot_runtime.py:69`（`append_log_file`）、`Goldenhandmaidens.py`（`clear_log_file`）

**验证**：单测——预置一个超限的假日志文件，调用一次 `append_log_file` 后断言产生了 `.1` 备份且主文件被重建。

### A8【中】版本与产物一致性（对应 D7-2）

**做法**：本次改动合入后把 `version.py` 升到下一个版本号，并在打包前确认 `CHANGELOG.md` 的「未发布」小节已归入该版本；GUI 标题栏/关于处显示 `__version__`（已有 `version_label`），无需改代码。

**文件**：`version.py`、`CHANGELOG.md`

**验证**：`python -c "import version; print(version.__version__)"` 与 CHANGELOG 最新小节一致；重编译后 exe 内嵌版本字符串与之一致。

### A9【中】补纯逻辑测试（对应 D5-1、D6-1）

**做法**：把本轮临时写过的 GUI 冒烟脚本产品化入库，并为新模块补可测逻辑：
- `test_gui_order.py`：重排后 `self.scripts` 与按钮 pack 顺序一致、`current_script_index` 跟随原选中项、`script_order` 持久化与恢复、配置缺新功能时补到末尾。
- `test_guild_flow.py`：`flow_enter_guild_play` 在"页签已激活/未激活/找不到卡片"三种匹配桩下的分支与返回值（monkeypatch `find_center_silent`）。
- `test_yuanwangdan_state.py`：`_panel_state` 的判定顺序与兜底分支（桩化匹配结果），`_wait_gone` 的消失/超时语义。
- 给 `test_smoke.py` 的 `start.py` 排除项补注释说明原因。

**文件**：新建 `tests/test_gui_order.py`、`tests/test_guild_flow.py`、`tests/test_yuanwangdan_state.py`、修改 `tests/test_smoke.py`

**验证**：`pytest -q` 全绿；故意反转一个判定顺序，对应测试必须失败。

### A10【低】整洁性批量清理（对应 D1-1、D1-3、D4-3、D3-4）

**做法**：①删除 8 个文件首行的 `# F:\afkj\...` 残留注释；②删 `common.py:29` 重复行；③`random_sleep` 上移到 `common.py` 并由 5 个文件引用；④README 第 139 行的行数改为不写死（写"最大文件，已拆分出 bot_runtime"）或更新为实测值；⑤README 功能表补上结社战线/狩猎悬赏两行。

**文件**：`common.py`、`flow_enter.py`、`meirirenwulingqu.py`、`shangcheng.py`、`shouquguajijiangli.py`、`start.py`、`youjian.py`、`youyishangcheng.py`、`flow_tower.py`、`mimengzhiyu.py`、`nvshenta.py`、`pata.py`、`pujing.py`、`README.md`

**验证**：`ruff check .` 告警数不增加；`grep -c "F:\\\\afkj" *.py` 为 0。

### A11【低】登记 lint 基线（对应 D7-4）

**做法**：为 `ruff` 建一份基线（`[tool.ruff]` 选定规则集 + 对存量 64 项按规则分组登记为 pending，或加 `--exclude` 明确不治理的历史文件），并在 README「代码规范」写明"新增代码不得引入新告警"。

**文件**：新建/修改 `pyproject.toml` 或 `ruff.toml`、`README.md`

**验证**：`ruff check .` 输出可被基线解释（新增告警会让命令失败）。

---

## 四、优先级与并行性

| 优先级 | 建议 | 并行组 | 理由 |
|---|---|---|---|
| P0 | **A1** 任务成败语义 | 组 α | 正在静默丢失用户每日收益，影响面最大 |
| P0 | **A2** 点击器存活探测 | 组 β | 与 A1 无文件重叠；直接消除排障黑洞 |
| P0 | **A3** 模板规范 + 机械校验 | 组 γ | 只新增文件，与 A1/A2 不冲突 |
| P1 | **A5** 统一弹窗关闭 | 组 β | 与 A2 同改 `common.py`，**必须串行**（先 A2 后 A5） |
| P1 | **A4** 注册单源化 | 组 α | 与 A1 同改 `Goldenhandmaidens.py`，**必须串行**（先 A1 后 A4） |
| P1 | **A6** 路径语义统一 | 组 γ | 改 `start.py` / `formation.py` / `flow_migong.py`，与 A1/A2/A5 无重叠 |
| P1 | **A9** 补纯逻辑测试 | 组 δ | 只新增 `tests/`，可与任意组并行；但 A1/A4/A5 的验证依赖它，**建议最先落 A9 的骨架** |
| P2 | **A7** 日志轮转 | 组 β | 改 `bot_runtime.py`，与 A2 部分重叠（GUI 侧），排在 A2 后 |
| P2 | **A8** 版本一致 | 组 γ | 独立 |
| P3 | **A10** 整洁清理 | 组 ε | 纯机械改动，可与任何组合并最后一次做 |
| P3 | **A11** lint 基线 | 组 ε | 独立 |

**可并行组划分（同组内文件无重叠，可并发执行）**

- 组 α：A1 → A4（串行，均涉 `Goldenhandmaidens.py`）
- 组 β：A2 → A5 → A7（串行，均涉 `common.py` / `bot_runtime.py`）
- 组 γ：A3、A6、A8（三者互不重叠，可并行）
- 组 δ：A9（仅 `tests/`）
- 组 ε：A10、A11

组 α / β / γ / δ / ε **之间**可并行，唯一硬约束是 A9 的测试骨架应先于 A1/A4/A5 的"验证"步骤完成。

---

## 五、审计中已确认"不是问题"的项（避免后续 Agent 重复排查）

- `find_center_silent` 无本地重复实现：全项目仅 `common.py:235,262` 两处定义，README 的去重声明成立。
- 任务脚本 `while` 循环未显式调用 `check_stop()` **不是缺陷**：停止检查注入在 `screenshot_bgr()` 与 `send_coord()` 两个底层原语中（`common.py` 注释已说明），F9 仍能穿透打断。
- `templates/` 中大量未引用的英雄 PNG 属正常：`warehouse.py` / `hero_metadata.py` 按英雄 ID 动态拼名，静态正则扫不到。
- 全屏模板匹配（不限定窗口区域）是有意设计：返回绝对屏幕坐标供 AHK 注入，窗口移动后仍有效。**但见下文 R1——该设计在未限定客户区时带来 3 倍开销，可保留语义同时消除开销。**

---

## 六、架构分支分析（software-improvement / architecture）

分层与依赖方向：`任务脚本 → common（感知/动作/恢复/日志/停止）→ pyautogui + OpenCV + 文件 IPC → click_from_file.exe`；
GUI 侧 `Goldenhandmaidens → bot_runtime → common`。依赖单向、无环。最热调用路径是
`common.find_center_silent`（每个状态判定轮都要跑 1–5 次全屏匹配）。

### 质量属性排查结论

| 方面 | 结论（定位到文件） |
|---|---|
| **性能** | `common.py:262 find_center_silent` 默认 `region=None`，对**整桌面**做匹配。实测桌面 3840×1080（4.15 MP）时单次匹配 **216–357 ms**，而游戏客户区只有 1600×900（1.44 MP）；限定客户区后降到 **73–106 ms（3.0–3.8x）**。`yuanwangdan._panel_state()` 一轮最多 5 次串行匹配 ≈ 1.3 s，`recover_to_main_interface` 每层 5 模板 × 8 层 ≈ 8 s，全部耗在扫描游戏画面之外的像素。另 `SCREENSHOT_CACHE_TTL=0.05s` 短于单次匹配耗时，缓存实际很少命中。 |
| **可维护性** | 见 D3-1（结果契约不统一）、D2-1（新增任务需改 3 处）、D4-5（像素魔数分散）。 |
| **可扩展性** | 新增一个日常任务的边际成本高：3 处注册 + 无模板规范 + 无测试骨架（D2-1/A3/A9）。`flow_gonghui.py` 已证明"共用入口"这条路可行，但只有公会两个任务在用。 |
| **资源使用** | `game_bot.log` 无轮转（D7-1）；`common._screenshot_cache` 常驻一帧 4.15 MP BGR（≈12 MB），限定客户区后可降到 ≈4 MB。 |

### 依赖与构建排查结论

- **循环依赖**：未发现。`common` 不反向依赖任何任务脚本。
- **过重依赖**：`opencv-python` 是必需的，但只用到 `matchTemplate/imread/resize`，无更轻替代（模板匹配是核心能力），判定为**不调整**。
- **划分合理性**：`Goldenhandmaidens.py` 1674 行仍偏大，但 `bot_runtime.py` 已拆出无 UI 依赖的部分；本次不再拆（收益低于风险）。
- **跨语言边界**：Python↔AHK 用文件传两个整数，开销可忽略，**无不必要序列化**。

### 复用率排查结论

- 相似模块：`random_sleep` 5 份重复（D3-4，建议合并）；各任务脚本的「点 wanfamulu → 点自己的入口」样板约 15 处重复（`flow_gonghui` 只覆盖了公会两个），建议后续把 `flow_enter_play(card_tpl, name)` 泛化为通用入口。
- 通用逻辑候选：`click_position` / `dismiss_popup_away_from` 本轮已下沉到 `common`；`_wait_gone` 目前只在 `yuanwangdan.py`，若 A2 的存活探测需要同类轮询，应一并上移。

### 建议（按收益/风险比排序，五要素齐全）

**R1｜模板匹配限定到游戏客户区** — 收益/风险比最高
- 现状：`common.py:262` 全屏匹配；实测单次 216–357 ms。
- 方案：在 `common` 增加 `_client_region()`（`win32` 取游戏窗口客户区并缓存），`find_center_silent` 在 `region` 未显式传入时默认用它；**未命中时刷新一次窗口矩形再试**，以兼容窗口移动；保留显式传 `region` 的行为不变。
- 预期收益：所有任务的状态判定轮提速 **约 3 倍**；长流程（推图/爬塔/迷宫/愿望单）整体墙钟时间同比例下降；缓存常驻内存降到约 1/3。
- 改动风险：窗口在两次匹配之间被拖动且恰好命中"刷新前"的间隙会漏判——用"未命中即刷新重试"兜底；多屏/无窗口场景需保留全屏回退。
- 验证：单测断言 `find_center_silent` 在无 `region` 入参时实际扫描面积 < 全屏面积；实测同一模板限定前后耗时比 ≥ 2.5x；跑一轮 `yuanwangdan.main()` 确认交付数不因区域收窄而下降。

**R2｜点击器存活探测，点击不再静默失败**（= A2）
- 现状：`common.py:444 send_coord` 在点击器退出时静默超时返回，调用方无法区分成功与空打（本轮实测被误导一次）。
- 方案：新增 `clicker_alive()`（写哨兵坐标看是否被消费）；`send_coord` 累计"未被消费"次数，连续 3 次即告警并置标志；GUI 每任务开始前探测一次，失败则尝试重新拉起。
- 预期收益：消除一类最难排查的故障模式（表现为"界面无变化"），排障成本从小时级降到秒级。
- 改动风险：哨兵坐标 `-1 -1` 若被某些点击器实现当成真实点击会移动光标——用当前光标位置作哨兵值规避。
- 验证：单测用临时文件模拟"不消费"，断言计数与告警触发；正常路径不告警。

**R3｜统一任务成败语义**（= A1）
- 现状：5 个流程函数无返回值、8 个 `_run_*` 硬编码 `return True`，失败会被记为完成并**自动取消勾选** `daily_reset` 脚本。
- 方案：流程函数返回 bool；runner 透传；无法判定时返回 False 并写日志。
- 预期收益：直接止住"每日任务被静默跳过"这一用户可感知损失（影响 5 个任务）。
- 改动风险：历史流程可能因返回 False 而"看起来变差了"（其实是在暴露既有失败）；需要同时确认 GUI 失败分支不阻断后续任务（现有逻辑已支持）。
- 验证：单测 monkeypatch 流程返回 False，断言 `enabled` 不被清除。

**R4｜统一弹窗关闭路径**（= A5）
- 现状：`dismiss_popup` / `click_blank_to_exit` 点底部居中，与多个面板主按钮重合。
- 方案：`dismiss_popup` 复用 `dismiss_popup_away_from`；兜底点改为左下 1/4。
- 预期收益：消除任务间清理误触发按钮的隐患（实测热区偏差仅 2–15 px）。
- 改动风险：个别界面左下区域有控件；需在改动后跑一轮全任务观察。
- 验证：单测断言点击坐标相对热区中心有预期偏移。

**R5｜配置与模板路径语义统一**（= A6）
- 现状：`get_resource_path`（打包内只读）被用于用户可编辑 JSON 与 `start.py` 的模板路径。
- 方案：JSON 改"工作目录优先、内置回退"；`start.py` 改用 `get_template_path`。
- 预期收益：打包后用户配置真正生效；登录任务在杀软清理 `_MEIPASS` 时不再单独失败。
- 改动风险：首次运行工作目录无 JSON 时须正确回退，否则读不到配置。
- 验证：单测在临时工作目录放同名 JSON，断言读到工作目录那份。


