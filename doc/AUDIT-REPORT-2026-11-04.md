# 项目全面审计：情况说明与改进建议（2026-11-04）

审计对象 `D:\workspace\afk-journey-merlin-auto`，分支 `main`，HEAD `e14f9e0`。
本文**只登记发现与建议，不改动任何代码**；每条建议都可拆给执行 Agent 独立开工，
文件清单与验证方式按「零背景 Agent 可直接照做」的标准写。

上一轮同类审计见 [AUDIT-REPORT-2026-11-02.md](AUDIT-REPORT-2026-11-02.md)（A1–A11）。
本文第 5 节给出那 11 条的当前状态，避免重复劳动。

---

## 一、现状描述（可观察事实）

**规模**

| 项 | 实测值 |
|---|---|
| 顶层 `.py` | 36 个文件，11,250 行 |
| 最大单文件 | `Goldenhandmaidens.py` 1,906 行 |
| 其余前列 | `common.py` 1,164 · `push.py` 941 · `warehouse.py` 889 · `flow_migong.py` 849 · `flow_tower.py` 814 |
| 测试 | 12 个测试文件，1,010 行，60 条用例 |
| 模板 | `templates/*.png` 326 张 |
| 文档 | 根 3 篇（README / CHANGELOG / CLAUDE）+ `doc/` 3 篇 |
| 被 git 跟踪 | 522 个文件 |
| GUI 功能项 | 21 个 `ScriptConfig` |

**结构**：无包目录，36 个模块全部平铺在仓库根；`common.py` 是共享底座（截图、模板匹配、
点击 IPC、弹窗关闭、主界面判据、模板路径解析）；每个玩法一个顶层脚本模块，由 GUI 的
`_run_script_dispatch` 按中文名分发；识别用 OpenCV `TM_CCOEFF_NORMED` 模板匹配，**项目内无 OCR**；
点击经文件 IPC 交给提权的 `click_from_file.exe`（AHK，仓库内无源码）。

**质量水平的可观察面**

- 文档密度高且与代码同源：README 功能表覆盖 21 个功能项中的 20 个；`doc/TEMPLATE-AUTHORING.md`
  与 `doc/LIVE-DEBUGGING.md` 存在且被 README/CLAUDE 引用，引用目标全部存在。
- 代码内**没有任何硬编码本机绝对路径**（`grep C:\Users|D:\workspace` 在 `*.py` 中零命中）。
- 被跟踪的 4 个 JSON（config / formations / grid_offsets / migong_config）内容为游戏内名称与
  像素偏移，**不含账号、令牌、路径、邮箱、电话等隐私**。
- lint 有稳定基线：`ruff check .` 全仓 64 条，`doc/LIVE-DEBUGGING.md` §7 写明基线数与
  逐文件比对方法。
- 无 CI 配置（`.github` 不存在），无统一构建入口（无 Makefile / build 脚本 / noxfile）。
- 无依赖清单：`requirements*.txt` / `pyproject.toml` / `setup.py` / `Pipfile` **均不存在**，
  而 `.gitignore` 里有 `!requirements.txt` 一行指向不存在的文件。
- 版本锚点：`version.py` = `v1.4.7`；`CHANGELOG.md` 的「未发布（Working）」段 369 行，
  **已发布版本段 0 个**。
- 测试触达面：36 个顶层模块中，被任一测试文件 import 的有 8 个
  （Goldenhandmaidens / bot_runtime / common / fanfanle / haoyoujiangli / hongbaolingqu /
  log_format / push）；**27 个模块零测试**。

---

## 二、问题清单（按七个维度，每条含位置 / 描述 / 严重程度 / 影响范围）

### 维度 1 · 文档一致性

| 编号 | 位置 | 描述 | 严重 | 影响范围 |
|---|---|---|---|---|
| D1-1 | README.md 功能表（14–30 行区） | GUI 有 `ScriptConfig("仓库管理")`，功能表**没有对应行**；21 个功能项 README 只写 20 个 | 低 | 新用户从 README 看不出仓库管理做什么、要不要开 |
| D1-2 | README.md:170 | 该处只给了历史数字「由约 1637 行降至约 1443 行（此后随功能增强又有增长）」，**全篇没有当前行数**；实测现在 1,906 行，读者极易把 1443 当成现状 | 低 | 拆分收益与当前规模都被低估，影响后续重构决策 |
| D1-3 | `.gitignore` 末段 `!requirements.txt` | 白名单指向**仓库里不存在的文件**，同时全仓没有任何依赖安装说明——文档与仓库真实状态互相打脸 | 中 | 与 D2-1 同根：换机器无法还原环境 |

本维度其余核对**未发现问题**（doc 引用完整、无硬编码路径、无隐私入库）。

### 维度 2 · 文档缺漏

| 编号 | 位置 | 描述 | 严重 | 影响范围 |
|---|---|---|---|---|
| D2-1 | 仓库根（缺文件） | **没有依赖清单，也没有「怎么装环境」的文档**。AST 扫全仓实际第三方 import：`certifi` `cv2` `keyboard` `numpy` `pyautogui` `pytest` `windows_capture`；构建/检查另需 `pyinstaller` `ruff` | **高** | 新机器 clone 后无法运行源码，只能跑打包 exe；任何后续 Agent 都要重新逆向依赖 |
| D2-2 | `Goldenhandmaidens.py` | 「如何新增一个任务功能」无文档，且事实上要改 4–5 处（见 D3-1），漏一处就是静默不执行 | 中 | 新功能的常见踩坑面 |
| D2-3 | `updater.py` `jiance.py` `launch_game.py` `drag_utils.py` `youyishangcheng.py` `flow_enter.py` `flow_push.py` `flow_gonghui.py` | 8 个模块在 README 结构清单里有名字，但没有任何行为/接口文档，也无测试 | 低 | 排障时只能读源码 |

### 维度 3 · 架构优化点

| 编号 | 位置 | 描述 | 严重 | 影响范围 |
|---|---|---|---|---|
| D3-1 | `Goldenhandmaidens.py`（实测 21 ScriptConfig + 21 dispatch 条目 + 21 `_run_*` 方法 + 7 `create_*_params` + params 分支） | **任务注册单源化未落地**（上一轮 A4）：加一个功能要在同一文件里改 4–5 处，彼此靠人工保持一致 | 中 | 漏改 dispatch → 功能在列表里但永不执行；漏改 params → 配置项丢失 |
| D3-2 | `common.py` 1,164 行 | 截图通路、模板匹配、点击 IPC、弹窗关闭、主界面判据、模板路径、异常类型全在一个模块里 | 中 | 任何底层改动都要回归全部流程；import 副作用多 |
| D3-3 | `fanfanle.py:91`、`yingxiongtingtang.py:69`、`hongbaolingqu.py:379` | **同一个原语实现了三遍**：无 OCR 场景下「某区域点击前后自匹配是否掉分」判定动作是否生效，各自带阈值常量（0.90 / 0.97 / 0.97）与轮询循环 | 中-高 | 2026-11-04 刚踩过「阈值压在噪声底上导致误判」，同一课要踩三次；经验无法共享 |
| D3-4 | `hongbaolingqu.py:337 _tap_into_panel`、`hongbaolingqu.py:195 _open_task_panel_via_hud`、`haoyoujiangli.py:64 _open_friends_via_hud` | **「点固定 HUD 点位 + 校验进入」三份实现且写法不一致**：两份用 `click_position(twice=True)`，一份用 `send_coord` × 2 + `sleep(0.4)` | 中 | 同一教训两种编码，后续改动容易只改一处 |
| D3-5 | `log_format.py` 模块级 `_task` | 由工作线程写、由 GUI `log()` 与 stdout tee 读的全局可变状态 | 低-中 | 若同时存在两个运行循环（GUI 运行中再单独跑一个脚本），细节行会被归到错误的任务下 |

### 维度 4 · 代码写法

| 编号 | 位置 | 描述 | 严重 | 影响范围 |
|---|---|---|---|---|
| D4-1 | `Goldenhandmaidens.py:1730`、`bot_runtime.py:134` | 两处**绕过 `log_format.format_body`** 直接 `append_log_file`：异常堆栈整段多行无时间戳、不归组；早期 `_PersistentStdout` 同样原样落盘。与本轮刚确立的「面板与文件同一份正文」约定冲突 | 中 | 最需要排错的崩溃现场，恰恰是格式最乱的一段 |
| D4-2 | `tests/test_smoke.py:16` | 排除 `start.py` 的判断 `f != "start.py"` 无注释说明原因（上一轮 D6-1 的遗留部分） | 低 | 后人不敢删也不敢改 |
| D4-3 | 全仓 | `try/except/pass` 12 处、`except Exception` 后接 `pass` 7 处；无裸 `except:` | 低 | 静默吞错，故障表现为「什么都没发生」 |
| D4-4 | 仓库根 `_tmp_click_srv.py`（91 行） | 2026-10-24 的临时提权点击服务残留，被 `.gitignore` 的 `_tmp_*` 覆盖；其存在理由（怀疑翻翻乐要长按）已于 11-04 实测推翻 | 低 | 读者会误以为有两套点击通路 |
| D4-5 | 模块命名 | 拼音与英文混用（`hongbaolingqu`/`fanfanle` vs `push`/`warehouse`/`updater`），且 `flow_push.py` 与 `push.py` 并存、职责需读码才分得清 | 低 | 检索与新人理解成本 |

本维度**未发现**功能性 bug 或时序违例（`_StdoutTee` 以 `sys.__stdout__` 为 `_orig`，
多次赋值不会造成链式重复写盘——已核实）。

### 维度 5 · 测试覆盖率

| 编号 | 位置 | 描述 | 严重 | 影响范围 |
|---|---|---|---|---|
| D5-1 | 27 个零测试模块 | 36 个模块仅 8 个被测试 import。零测试里包含**每天真正跑的主流程**：`warehouse` 889 行、`flow_migong` 849、`flow_tower` 814、`yuanwangdan` 472、`nvshenta` 361、`pujing` 309、`mimengzhiyu` 295、`shouquguajijiangli` 221、`jieshezhanxian` 191、`lieshouxunshang` 173 | **高** | 这些模块坏了只能实机发现，而实机验证有**账号成本**（消耗门票、扫荡次数、派遣），不能反复试错 |
| D5-2 | `tests/` | 上一轮 A9 明确建议的 `test_guild_flow.py`、`test_yuanwangdan_state.py` 至今未创建 | 中 | 公会流程与愿望单状态机仍无保护 |
| D5-3 | `Goldenhandmaidens.py:1640-1745` | 运行循环 `run_scripts_thread`（成败语义、状态标注、任务归组、点击器探测）**没有任何用例**，而它本轮被改过两次 | 中 | 回归只能靠整轮实跑 |

### 维度 6 · 测试严谨性

| 编号 | 位置 | 描述 | 严重 | 影响范围 |
|---|---|---|---|---|
| D6-1 | 全测试目录 | 断言密度整体合格（每个文件 ≥1 断言/用例，最高 `test_push_fail_limit.py` 7 用例 21 断言）；但 `test_smoke.py`（2 用例 3 断言）与 `test_templates.py`（3 用例 3 断言）偏薄，前者主用例只断言「import 不抛异常」 | 中 | 「跑通即通过」，测不出行为回归 |
| D6-2 | 无 CI | pytest / ruff 全靠人手工跑；「lint 零新增」只是文档约定，没有机械门禁 | 中 | 忘记跑就合进去 |
| D6-3 | `tests/conftest.py` | GUI 用例依赖真实 Tk；无显示环境时靠 `pytest.skip` 整组跳过（实测会静默少跑 4 条）。跳过是**无声**的 | 低 | 「全绿」可能包含被跳过的关键用例 |

### 维度 7 · 工程规范

| 编号 | 位置 | 描述 | 严重 | 影响范围 |
|---|---|---|---|---|
| D7-1 | `version.py` + `CHANGELOG.md` | 版本仍 `v1.4.7`，而「未发布」段已积累 **369 行、已发布版本段 0 个**——大量已实机验证的功能没有版本锚点 | **高** | 无法回答「这个行为是哪一版引入的」；回滚没有落点；打包产物与源码版本无法对应 |
| D7-2 | 仓库根 | 无统一构建入口：打包命令只写在 `doc/LIVE-DEBUGGING.md` §8 的正文里；也没有 clean 目标（构建产物 `build/` 只能手删） | 中 | 命令漂移、易漏参数、易误用 `rm` 清缓存 |
| D7-3 | `.gitignore` | `*.txt` 全局忽略 + 仅白名单 `requirements.txt`（还不存在）→ 未来任何 `.txt` 数据文件都会被**静默忽略**；`.pytest_cache/`、`.ruff_cache/` 只靠工具自己在目录内写的 `.gitignore` 兜住，仓库自身规则未登记 | 低 | 换工具版本或新机器时缓存可能被提交；数据文件可能悄悄没入库 |
| D7-4 | `doc/LIVE-DEBUGGING.md` §7 | lint 基线写成「约 64 条」的散文，没有机器可读的基线文件 | 低 | 基线漂移无人察觉 |

---

## 三、改进建议（逐条：做法 / 涉及文件 / 验证方式）

### B1【高】补依赖清单与安装文档（对应 D2-1、D1-3）— ✅ 已执行（见第七节）

**做法**
1. 新建 `requirements.txt`，按 AST 扫描结果分两组写死可复现版本（本机实测版本）：
   运行依赖 `opencv-python==5.0.0.93`、`numpy==2.5.3`、`pyautogui==0.9.54`、
   `keyboard==0.13.5`、`windows-capture==2.0.1`、`certifi`；
   开发依赖另列 `requirements-dev.txt`：`pytest==9.1.1`、`ruff==0.16.10`、`pyinstaller==6.22.3`。
2. README 增加「环境准备」小节：Python 版本、`pip install -r requirements.txt`、
   以及**必须以管理员运行游戏 → 点击器需提权**这一硬约束（现散落在 `doc/LIVE-DEBUGGING.md` §1）。
3. `.gitignore` 的 `!requirements.txt` 保留（此时它才真正生效），并补 `!*.txt` 的例外说明或改用
   更窄的忽略规则（见 B8）。

**涉及文件**：`requirements.txt`（新）、`requirements-dev.txt`（新）、`README.md`、`.gitignore`
**验证方式**
- 新建干净 venv，`pip install -r requirements.txt -r requirements-dev.txt` 成功；
- 该 venv 内 `python -c "import Goldenhandmaidens"` 无 ImportError；
- 该 venv 内 `pytest -q` 全绿（60 条）；
- `pip freeze` 与清单逐项比对，无遗漏第三方模块（用第 5 节的 AST 扫描脚本复算）。

---

### B2【高】把「无 OCR 区域变化检测」抽成单一原语（对应 D3-3）

**做法**
1. 在 `common.py` 增加一个函数（签名建议）：
   `region_changed_since(before_crop, region, *, threshold, timeout=3.0, interval=0.4) -> bool`，
   内部做「客户区裁剪 + `TM_CCOEFF_NORMED` + 轮询到超时」，并把 `check_stop()` 放进循环。
2. 三个调用点改为复用：`fanfanle._wait_keys_change`、`yingxiongtingtang._wait_level_change`、
   `hongbaolingqu._row_changed`；**各自的阈值常量与区域常量保留在调用方**（阈值是界面相关的，
   不能合并成一个全局数）。
3. 在 `doc/LIVE-DEBUGGING.md` §5.1 补一句：该原语的阈值必须**低于实测噪声底**，
   并要求新调用点在注释里写下「静止 X / 真变化 Y」两个实测数（本轮已有三组数据可直接引用）。

**涉及文件**：`common.py`、`fanfanle.py`、`yingxiongtingtang.py`、`hongbaolingqu.py`、
`tests/test_common_region_change.py`（新）
**验证方式**
- 现有 `test_fanfanle.py`（6 条）、`test_hongbaolingqu.py`（7 条）全绿，且**不改断言**；
- 新用例：同一帧自匹配返回 False；把裁剪区域整体平移 ≥1px 后返回 True；
- 反向验证：把 `region_changed_since` 的返回值写死 True/False，对应模块用例必须失败。

---

### B3【高】按「每天真跑」的顺序补纯逻辑测试（对应 D5-1、D5-2、D6-1）— ✅ 已执行（见第七节）

**做法**：只测**不依赖真实窗口的纯逻辑**，用 monkeypatch 桩掉 `find_center*` / `screenshot_bgr` /
`click_position`（仓库已有这套写法可抄：`test_hongbaolingqu.py`、`test_push_fail_limit.py`）。优先级：
1. `warehouse`（889 行）——英雄识别结果聚合与练度判定；
2. `yuanwangdan`（472 行）——`_panel_state` 判定顺序与 `_wait_gone` 超时语义（上一轮 A9 原题）；
3. `flow_tower`（814 行）/ `flow_migong`（849 行）——状态机跳转表与失败上限；
4. `test_smoke.py` 的 import 用例补一条真实断言（例如断言模块暴露 `main()` 且可调用），
   并给 `start.py` 排除项补注释（对应 D4-2）。

**涉及文件**：`tests/test_warehouse_logic.py`、`tests/test_yuanwangdan_state.py`、
`tests/test_flow_tower_pure.py`、`tests/test_flow_migong_pure.py`、`tests/test_smoke.py`
**验证方式**
- `pytest -q` 全绿；
- **每条新用例都要做反向验证**：故意反转一个判定，用例必须失败（`doc/LIVE-DEBUGGING.md` §7 已立此规矩）；
- 统计口径：被测试 import 的模块数从 8 提升到 ≥13。

---

### B4【中】任务注册单源化（对应 D3-1、D2-2，闭环上一轮 A4）

**做法**：把 `ScriptConfig` 从「名字 + 参数」扩成自带注册信息，使 dispatch 与参数面板可派生：
- `ScriptConfig(name, enabled, params, runner="module:function", param_spec=(label, lo, hi, default))`；
- `_run_script_dispatch` 改为按 `runner` 字符串 import 并调用，删掉 21 条手写 `self._run_*`；
- 参数面板按 `param_spec` 自动生成 Spinbox，删掉 `create_*_params` 的逐处分支；
- 保留 `ScriptConfig` 现有字段与配置文件格式，**不改 `game_bot_config.json` 的 schema**（避免用户配置迁移）。

**涉及文件**：`Goldenhandmaidens.py`、`bot_runtime.py`（`ScriptConfig` 定义）、
`tests/test_gui_order.py`、`tests/test_gui_status_display.py`、README（功能表 + 新增「如何加一个功能」小节）
**验证方式**
- 现有 GUI 用例全绿，且 `test_gui_order.py` 的「六份集合同序」断言仍成立；
- 新增一条用例：只往列表里追加一个带 `runner` 的假功能，断言它出现在列表、可勾选、
  且 dispatch 能命中（桩掉真实模块）——**证明只需改 1 处**；
- 手工核对：`grep -c "ScriptConfig(\""` 与 dispatch 条目数不再需要同时 +1。

---

### B5【中】日志出口彻底统一（对应 D4-1）

**做法**：让所有落盘路径都过 `log_format.format_body`。
1. `Goldenhandmaidens.py:1730` 的堆栈改为按行拆分后逐行走 `log()`（或
   `append_log_file` + `format_body`），使每行带时间戳并归到当前任务下；
2. `bot_runtime._PersistentStdout.write` 同样按行缓冲并走 formatter（与 `_StdoutTee` 共用一个
   行缓冲实现，避免两份）；
3. `log_format` 增加 `format_multiline(text) -> list[str]` 供堆栈这类多行文本使用。

**涉及文件**：`Goldenhandmaidens.py`、`bot_runtime.py`、`log_format.py`、
`tests/test_log_format.py`、`tests/test_log_sink_persist.py`
**验证方式**
- 新用例：喂一段 3 行 traceback，断言落盘得到 3 行、每行匹配 `^\[\d\d:\d\d:\d\d\] `、
  且任务上下文非空时都带 detail 缩进；
- 现有 `test_log_timestamps.py` / `test_log_sink_persist.py` 全绿；
- 实机：`python -u -c "import Goldenhandmaidens as g; g.GameBotGUI(...)"` 触发一次异常路径，
  读 `game_bot.log` 确认堆栈行已带戳（或直接用临时 LOG_FILE 断言）。

---

### B6【中】HUD 固定点位入口收敛为一个 helper（对应 D3-4）

**做法**：在 `common.py`（或 B2 的同一批改动里）加
`tap_hud_entry(client_pos, *, confirm, retries=2, wait=2.0) -> bool`：
内部做「客户区原点换算 + 连点两下（首次被激活吞掉）+ `confirm()` 校验 + 重试」，
`haoyoujiangli._open_friends_via_hud`、`hongbaolingqu._open_task_panel_via_hud`、
`hongbaolingqu._tap_into_panel` 三个实现改为复用。**保留各自的 confirm 判据**（界面相关）。

**涉及文件**：`common.py`、`hongbaolingqu.py`、`haoyoujiangli.py`、`fanfanle.py`
**验证方式**
- `test_haoyoujiangli.py`（3 条，含「坐标必须加客户区原点」「重试不漂坐标」）与
  `test_hongbaolingqu.py`（兜底入口那条）全绿且不改断言；
- 新用例：confirm 恒 False 时，helper 必须在 retries 用尽后返回 False，且调用次数 = retries×2。

---

### B7【中】建立版本与发布锚点（对应 D7-1，闭环上一轮 A8）

**做法**
1. 把 `CHANGELOG.md` 的「未发布（Working）」369 行按功能切成版本段（建议 `v1.5.0`：
   红点领取体系 + 翻翻乐 + 英雄厅堂 + 日志体系；`v1.5.1`：判据与入口修正）；
2. `version.py` 同步升到对应版本；
3. README 顶部「版本」一行引用当前版本；
4. 之后每次发布：改 CHANGELOG → commit → push → 打 tag（可复用 `git-release` skill 的流程）。

**涉及文件**：`CHANGELOG.md`、`version.py`、`README.md`
**验证方式**
- `python -c "from version import __version__; print(__version__)"` 与 CHANGELOG 最新段一致；
- CHANGELOG 中「未发布」段行数降到 <40（只剩真正未发布的）；
- `git tag --sort=-v:refname | head -3` 有锚点，且 `git log <tag>..HEAD --oneline` 可回答
  「某功能之后又改了什么」。

---

### B8【中】统一构建入口与清理目标（对应 D7-2、D7-3）

**做法**：新增 `build.ps1`（或 Makefile）提供三个目标：
`build`（PyInstaller 用现有 spec 与参数）、`check`（`compileall` + `pytest -q` +
`ruff check .` 并与基线比对）、`clean`（清理 `build/`、`dist/`、`__pycache__`、`.pytest_cache`、
`.ruff_cache`）。**清理逻辑封装进构建脚本**，不在命令行里直接 `rm`。
同时把 `.pytest_cache/`、`.ruff_cache/` 显式写进 `.gitignore`，并把 `*.txt` 规则收窄
（改成只忽略已知产物，避免未来任何 `.txt` 数据文件被静默忽略）。

**涉及文件**：`build.ps1`（新）、`.gitignore`、`doc/LIVE-DEBUGGING.md` §7–8、README
**验证方式**
- `pwsh -NoProfile -File build.ps1 check` 退出码 0，且输出含「64 条基线一致」；
- `pwsh -NoProfile -File build.ps1 build` 产出的 exe 能被
  `PyInstaller.archive.readers.CArchiveReader` 解包，且 PYZ 内含 `log_format` 等全部顶层模块；
- `pwsh -NoProfile -File build.ps1 clean` 后 `git status --porcelain --ignored` 中无缓存目录残留；
- 新建一个临时 `foo.txt` 后 `git check-ignore -v foo.txt` 不再命中（证明规则已收窄）。

---

### B9【低】lint 基线登记为机器可读文件（对应 D7-4、D6-2）

**做法**：新增 `.ruff_baseline`（每行 `文件=条数`，当前：common 4 / Goldenhandmaidens 32 /
bot_runtime 11 / 全仓 64），并让 B8 的 `check` 目标读取它做逐文件比对；
在 CI 缺位的情况下，把「提交前跑 check」写进 `CLAUDE.md` 的项目段（当前 CLAUDE.md 是通用行为
准则，无项目专属门禁）。

**涉及文件**：`.ruff_baseline`（新）、`build.ps1`、`CLAUDE.md`、`doc/LIVE-DEBUGGING.md` §7
**验证方式**：故意在某文件引入一条新 ruff 告警 → `build.ps1 check` 必须失败并指名该文件。

### B10【低】整洁性收尾（对应 D4-4、D4-5、D3-5、D5-3）

**做法**：① 经用户确认后移除 `_tmp_click_srv.py`（其存在理由已被实测推翻）；
② 给 `log_format._task` 补一行注释说明「单运行循环假设」，并在 GUI 启动新循环前断言
`current_task() is None`；③ 让 GUI 用例在**无 Tk 环境**时输出显式 warning 而非静默 skip
（`conftest.py` 里把 `pytest.skip` 换成带原因的 `warnings.warn` + skip）；
④ 命名不做批量重命名（收益低、风险高），只在 README 结构清单里给 `flow_*` 与非 `flow_*`
的分工写一句说明；
⑤ README 功能表补「仓库管理」一行（对应 D1-1）；
⑥ README:170 那句改成「当前约 1,900 行，历史：由约 1637 行拆分降至约 1443 行」——
保留历史叙事，但把**当前值**写出来（对应 D1-2）。

**涉及文件**：`_tmp_click_srv.py`（删除，需确认）、`log_format.py`、`tests/conftest.py`、`README.md`
**验证方式**：`pytest -q` 全绿；在无显示环境（或强制 `TclError`）下跑一次，确认跳过被显式报出；
`grep -c "仓库管理" README.md` ≥ 1，且 README 里出现当前行数量级。

---

## 四、优先级与并行性

| 优先级 | 建议 | 可并行组 | 理由 |
|---|---|---|---|
| **P0** | B1 依赖清单 | **组 1**（与其他组文件不重叠） | 阻塞一切「换机器 / 新 Agent」工作 |
| **P0** | B3 补纯逻辑测试 | **组 2**（只新增 tests/*，与 B1 不重叠） | 每天真跑的主流程无保护，且实机验证有账号成本 |
| **P1** | B2 区域变化检测单源化 | **组 3**（动 common + 3 个流程模块） | 同一课已踩一次，三处实现会各踩一次 |
| **P1** | B5 日志出口统一 | **组 4**（动 Goldenhandmaidens + bot_runtime + log_format） | 崩溃现场格式最乱，直接影响排障 |
| **P2** | B7 版本与发布锚点 | **组 5**（动 CHANGELOG / version / README） | 与 B5/B8 的 README 有重叠 → 与它们串行 |
| **P2** | B6 HUD 入口 helper | **依赖 B2**（同改 common 与 hongbaolingqu/haoyoujiangli） | 需串行，排在 B2 之后 |
| **P2** | B8 构建入口 + ignore 收窄 | **依赖 B5**（同改 bot_runtime）；与 B7 共享 README → 排 B5/B7 之后 | |
| **P3** | B4 任务注册单源化 | **依赖 B5**（同改 Goldenhandmaidens.py） | 收益大但改动面最广，必须串行且先有 B3/B5 的保护网 |
| **P3** | B9 lint 基线文件 | 依赖 B8（由 `check` 目标消费） | |
| **P3** | B10 整洁性收尾 | 组 6（除删除动作外文件独立） | 删除 `_tmp_click_srv.py` **需用户明确确认** |

**并行执行建议**：组 1 + 组 2 + 组 3 + 组 4 可同时开工（已核对文件集合互不相交）。
组 5/6 及 B4/B6/B8/B9 之间存在文件重叠，按上表依赖顺序串行。

**执行纪律**：进入改动阶段时按 `software-improvement` 的分支走——B2/B4/B6 属**架构**分支，
B3 属**测试**分支，B5/B9/B10 属**代码质量**分支，B1/B7/B8 属**工程规范/文档**分支；
**一次任务只走一个分支**，每改一点立刻 `pytest -q` 全绿再继续。

---

## 五、上一轮（2026-11-02）A1–A11 的当前状态

| 上轮编号 | 主题 | 状态 | 依据 |
|---|---|---|---|
| A1【高】 | 任务成败语义统一 | **已闭环** | `_run_script_dispatch` 返回 bool，状态色覆盖 运行中/等待中/完成/失败/错误/已停止 |
| A2【高】 | 点击器存活探测 | **已闭环** | `clicker_alive()` + `ClickerNotRunning`，`test_clicker_guard.py` 6 条 |
| A3【高】 | 模板规范 + 机械校验 | **已闭环** | `doc/TEMPLATE-AUTHORING.md` + `tests/test_templates.py` 3 条 |
| A4【中】 | 任务注册单源化 | **未闭环** → 本轮 B4 | 实测仍需 21 ScriptConfig + 21 dispatch + 21 `_run_*` + 7 `create_*_params` |
| A5【中】 | 统一弹窗关闭 | **已闭环** | `common.dismiss_popup` / `dismiss_popup_away_from`，调度循环统一调用 |
| A6【中】 | 配置与模板路径语义 | **部分闭环** | `get_work_path` 已统一；APPDATA 模板副本仍靠约定 |
| A7【中】 | 日志轮转 | **已闭环** | `MAX_LOG_BYTES = 5MB`，`.1` 单份备份，有测试 |
| A8【中】 | 版本与产物一致性 | **未闭环** → 本轮 B7 | version 仍 v1.4.7，未发布段 369 行、已发布段 0 |
| A9【中】 | 补纯逻辑测试 | **部分闭环** → 本轮 B3 | push/hongbaolingqu/fanfanle/haoyoujiangli/gui/log 已有；`test_guild_flow`、`test_yuanwangdan_state` 仍未创建 |
| A10【低】 | 整洁性批量清理 | **部分闭环** → 本轮 B10 | `_tmp_click_srv.py` 仍在仓库根 |
| A11【低】 | 登记 lint 基线 | **部分闭环** → 本轮 B9 | 基线写在 `doc/LIVE-DEBUGGING.md` §7（约 64 条），无机器可读文件 |

---

## 六、审计中已确认「不是问题」的项（避免后续 Agent 重复排查）

- **无隐私入库**：被跟踪的 4 个 JSON 只含游戏内名称与像素偏移；`.gitignore` 已排除
  `game_bot_config.json`、`game_bot.log`、`warehouse_heroes.txt`、`shared/`。
- **代码中无硬编码本机路径**：`C:\Users` / `D:\workspace` 在 `*.py` 中零命中；README 里的
  `schalkiii/afk-journey-merlin-auto` 是公开仓库地址，属应有信息。
- **`_StdoutTee` 不存在链式重复写盘**：`_orig = sys.__stdout__`，多次重新赋值不会叠加包装，
  一次 print 只落一行（`test_log_timestamps.py` 已守此性质）。
- **无裸 `except:`**；`try/except/pass` 数量见 D4-3，属可读性问题而非静默致命错误。
- **通用礼包角标检测**：已六次实测否决（跨界面缩放不同 + HUD 脉动动画），
  详见 `doc/TEMPLATE-AUTHORING.md` §2 与 CHANGELOG；**不要再试第七种**。
- **玩法目录卡片盲栅格**：已整段撤销，会误闯带自动派遣倒计时的活动页且恢复不可靠。
- **翻翻乐不需要长按**：一次单击连抽到本轮 100 满；进度数字每满 100 归零，
  判据必须用钥匙余量（`fanfanle.py` 已按此实现）。
- **测试不污染产品日志**：`tests/conftest.py` 会话级夹具已把 `LOG_FILE` 指向临时目录，
  实测一次 pytest 前后计数不变。

## 七、执行进展（2026-11-04 晚间，B1 与 B3 已落地）

**B1 依赖清单**：新增 `requirements.txt`（运行时）与 `requirements-dev.txt`（pytest / ruff / pyinstaller），
按本机 Python 3.13.17 实盘 `==` pin。三个 opencv 发行版共存于 site-packages，据运行时 cv2 同时含 contrib
独有模块与 GUI、且 `cv2.pyd` 时间戳与 `opencv_contrib_python` 的 dist-info 一致（晚于另两个），判定生效者为
**opencv-contrib-python**；清单只保留它并注明「只装一个发行版」。另查出建议中未列的隐藏依赖
`keyboard`（`Goldenhandmaidens.py:1345`）与 `certifi`（`updater.py:17`），以及 `psutil` 全仓零 import 的事实。
README「运行环境 / 二次开发」的 `pip install ... requests pillow opencv-python` 一行有误（requests 从未 import、
pillow 仅传递依赖），已改为按清单安装。

**B3 补测试**：用例 60 → **106**。`test_yuanwangdan`(18) / `test_warehouse`(9) / `test_flow_migong`(12) /
`test_flow_tower`(5) + `test_smoke` 加强 2 条，覆盖建议里点名的四个模块。度量口径据实际情况修正：建议原文写的
「modules imported by tests: 8 → ≥13」把 `test_smoke.test_all_modules_import` 的 importlib 全量导入误当成了覆盖，
真实口径应为「tests 目录里显式 import 且有断言的产品模块」，**7 → 11**。

**执行中的偏差与产出（原建议未预见）**：

- **唯一无法负验证的一条**：`find_all_instances_mg` 的 `loc.sort(key=y)`（`flow_migong.py:263`）。函数体是按
  (y, x) 升序的双层扫描，发现顺序天然已按 y 递增，删掉该 sort 不会让用例变红——**这行当前是恒等操作**。
  用例保留，改为守 B4（向量化后行序不保证）这条防线，测试内已写明理由。这比原建议的措辞更准确：
  sort 不是必需的契约，而是冗余保险。
- **由新测试暴露并修掉**：`yuanwangdan.py:309` 的 `_find(tpl_wish_label, 0.85)`——`_find` 的第二位置参数是
  `timeout`，裸写极易被读成「阈值 0.85」。改为显式 `timeout=0.85`，**运行时行为完全不变**（若要真收紧该阈值，
  需实跑验证后另行改动，与待办 #14 同类）。
- **清单落地时踩到的仓库级坑**：`.gitignore` 有 `*.txt` 而只反选 `!requirements.txt`，`requirements-dev.txt`
  会被静默忽略、clone 后拿不到。已改为 `!requirements*.txt`。建议 B1 未预见这一条。
- **新登记三项（本次不改，均在补测试分支范围外）**：`warehouse.has_fancy_border`（:469）主流程未调用、疑似遗留；
  零方差 / 纯色图上 `cv2.matchTemplate` 返回 1.0，模板全黑时会「满分命中」，`_recognize_hero` 的阈值拦不住；
  `flow_tower.py:84` 的 `SPECIAL_HERO_SET` 为空集，使特殊角色分支在该模块不可达（仅 `push.py:68` 有内容）。
- **附带证据**：单测里 `find_all_instances_mg` 的桩图必须压到 20×24 量级（真机 `res` 约 1596×896 ≈ 143 万次循环），
  这为 **B4 的双层循环性能项**提供了可复现的量级证据。

**门禁**：`python -m compileall .` 通过；`pytest -q` 106 passed；`ruff check .` 64 条 = 存量基线，新增测试文件
自身 0 条。产品代码本次只动了上述一行显式化。B2、B4–B10 未动。
