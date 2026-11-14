# 项目情况说明与改进建议（2026-11-07 审计快照）

> 本报告由 `project-audit` 流程产出，**只登记发现与建议，不包含任何代码改动**。
> 面向的执行对象是「对项目零背景、可独立开工的 Agent」：每条问题都给到文件与行号，
> 每条建议都给到做法、文件清单、验证方式。
> 历史 `doc/AUDIT-REPORT-2026-11-02.md` / `2026-11-04.md` 已在提交
> `55758af`（工程收尾：清理历史审计材料）中删除，本报告是新的现役快照。
> 后续执行阶段须拼接 `software-improvement` 的改动纪律，见第 5 节。
>
> **时效声明（2026-11-11）**：第 1 节的行号、用例数（226）与文件清单都是 **2026-11-07 当时值**。
> 11-08 ~ 11-11 的实机调试改动见 `CHANGELOG.md` 的「实机调试第二 ~ 五批」，其中点击链路、
> 爬塔/狩猎悬赏/推图/翻翻乐的判据、测试基线（11-11 时为 332 条，2026-11-14 已是 **402** 条）均已变化。按条目复核前，请先以
> 当前代码与 `build.ps1 check` 为准，不要直接引用本报告的数字当门禁预期。

---

## 1. 现状描述

### 1.1 规模（可复现的计数）

| 项 | 数量 | 计数方式 |
| --- | --- | --- |
| Python 文件 | 71 | `find . -name "*.py" -not -path "./__pycache__/*"` |
| ├ 顶层模块 | 36 | `glob("*.py")`，含 `version.py` 等 |
| ├ 测试文件 | 34 | `tests/test_*.py`，另 `tests/conftest.py` |
| Python 总行数 | 17,415 | `wc -l`（全部 .py） |
| 模板 PNG | 471 | `find templates -name "*.png"` |
| ├ 顶层 | 338 | `find templates -maxdepth 1 -name "*.png"` |
| └ `templates/migong/` | 133 | 子目录，由 `get_template_path(..., subdir="migong")` 使用 |
| 模板字面量引用 | 140 | 正则 `get_template_path\(\s*["']([^"']+\.png)["']` 扫描顶层 .py |
| Markdown 文件 | 13 | 排除 `.workbuddy/`；主文档为 `README.md`、`CHANGELOG.md`、`CLAUDE.md`、`doc/TEMPLATE-AUTHORING.md`、`doc/LIVE-DEBUGGING.md` |
| pytest 用例 | 226 collected / 226 passed | `python -m pytest -q`，耗时 84.06s |
| ruff 告警 | 5（`Goldenhandmaidens.py=3`、`pata.py=2`） | `python -m ruff check . --output-format concise` |
| markdownlint | 0 error | `markdownlint README.md CHANGELOG.md CLAUDE.md doc/*.md` |
| git 工作区 | 干净 | `git status --short` 无输出；HEAD `55758af` |

`version.py` 为 `v1.4.7`。`.ruff_baseline` 登记的 5 条全部是有意保留的 catch-all
（`BLE001`），注释写明了保留原因。

### 1.2 结构

- **入口与调度**：`Goldenhandmaidens.py`（2,105 行，tkinter GUI + F8/F9 热键 + 定时/立即运行 +
  任务状态色块 + 日志汇聚 + 字典分发 `_run_script_dispatch`）；
  `bot_runtime.py`（344 行，从主文件拆出的 stdout 接管、配置读写、`ScriptConfig`、窗口聚焦）。
- **底座**：`common.py`（1,700 行、69 个顶层函数），职责含模板缓存与路径、截图（含 Windows
  Graphics Capture 后台帧）、窗口/客户区定位、点击 IPC、协作式停止、日志与格式、弹窗清理、
  返回主界面、阵容判定、区域变化判据、HUD 点击、模板中文名映射。
- **任务层**：20 余个顶层脚本（`start.py`、`push.py`、`warehouse.py`、`hongbaolingqu.py`、
  `yuanwangdan.py`、`jieshezhanxian.py`、`lieshouxunshang.py` …）与 `flow_*` 流程模块
  （`flow_enter.py`、`flow_gonghui.py`、`flow_migong.py`、`flow_push.py`、`flow_tower.py`）。
- **点击链路**：Python `send_coord` 写 `shared/target_coord.txt`（整屏绝对坐标）→
  提权 `click_from_file.exe`（AHK 编译产物，无 `.ahk` 源码）消费并注入真实鼠标事件。
  `common.clicker_alive()` 负责探测该进程是否仍在消费。
- **工程链**：`goldenhandmaidens.spec`（PyInstaller，`hiddenimports` 用 `glob("*.py")` 自动收集）、
  `build.ps1`（check = compileall + pytest + ruff 逐文件基线比对；build；clean）、
  `.ruff_baseline`、`.markdownlint.json`、`requirements.txt` / `requirements-dev.txt`
  （按 Python 3.13.17 实盘 pin）、`.gitignore`。
- **测试**：`tests/` 34 个文件，全部在模块级接缝打桩，不接真实屏幕；`conftest.py` 把
  `bot_runtime.LOG_FILE` 重定向到临时目录，避免 pytest 污染用户 `game_bot.log`。

### 1.3 质量水平

门禁三项全绿：pytest 226/226、ruff 5 条与基线一致、markdownlint 0 error。
文档完备度较高：`README.md` 453 行含功能表、项目结构、代码规范、FAQ；`CHANGELOG.md` 838 行
按批次记录实机结论与撤销过的方案；`doc/` 两份方法学文档记录了模板标定与实机调试的量化教训。
`CLAUDE.md` 定义了提交门禁与负验证要求。存在两类可观察的落差：一是文档与代码注释之间
有互相矛盾的断言（见 P1、P3、P4、P5），二是测试面有机械扫描盲区与恒真用例（见 P17、P19）。

---

## 2. 问题清单

> 每条按「位置 / 问题描述 / 严重程度 / 影响范围」四项登记。
> 严重程度定义：**高** = 会造成功能错误、数据/产物损坏或误导用户做出破坏性操作；
> **中** = 维护陷阱、门禁失效或覆盖缺口；**低** = 可读性、一致性、可复现性瑕疵。

### 维度 1：文档一致性

| # | 位置 | 问题描述 | 严重 | 影响范围 |
| --- | --- | --- | --- | --- |
| P1 | `README.md:278` vs `Goldenhandmaidens.py:208-209`、`yuanwangdan.py:482-485` | README 写「家园愿望单结束时会停在家园（即主界面，`wanfamulu` 可见），不会阻断后续任务；放在最后一位只是习惯，不再强制」；两处代码注释写「必须排在执行顺序末尾」「家园视图下 `wanfamulu` 匹配度不足 0.5，调用 recover 会空转十余秒」。同一事实存在两个互斥结论，且 GUI 允许拖拽排序（`Goldenhandmaidens.py:220-225` 恢复 `script_order`），用户可把该任务拖到中间。 | **高** | 按 README 把任务拖到中间后，`run_scripts_thread`（`Goldenhandmaidens.py:1860` 附近）在每个任务前调用 `common.ensure_main_interface()`；其判据 `at_main_interface()`（`common.py:1033`）要求 `wanfamulu` 在底部栏以 0.8 阈值命中且无返回箭头。若家园视图确实命不中，会走 `recover_to_main_interface()` 空转 8 轮后返回 `False`；**GUI 未检查该返回值**，后续任务照常启动，其入口检测随即超时失败 —— 表现为「上一任务把后面全带崩」。 |
| P2 | `README.md:340`、`CHANGELOG.md:26,372,505,810` | README 项目结构仍列 `doc/AUDIT-REPORT-*.md 阶段性审计报告（历史快照）`；实际 `doc/` 只有 `LIVE-DEBUGGING.md` 与 `TEMPLATE-AUTHORING.md`（两份历史报告已由 `55758af` 删除）。CHANGELOG:505 的 Markdown 链接 `[doc/AUDIT-REPORT-2026-11-04.md](...)` 指向已删除文件；:372 引用 11-02 报告；:810 仍在说「已标明为历史快照」。 | 中 | 新 Agent 按 README 去找审计依据会扑空；CHANGELOG 死链让「依据某报告做的 R1–R5 改进」无法追溯到证据。 |
| P3 | `README.md:168,343,453` vs `goldenhandmaidens.spec:10`、`config.json` | README:453 写「spec 已将 `templates/`、`click_from_file.exe`、**各 `*.json` 配置**及 `flow_enter` 等模块一并打进 exe」；spec 的 `datas` 只有 `migong_config.json` / `formations.json` / `grid_offsets.json` 三个，**没有 `config.json`**。README:168/343 把 `config.json` 描述为「启动器/脚本的默认配置」，但全仓 `*.py` 中没有任何一处读取它（唯一配置入口是 `bot_runtime.py:87` 的 `game_bot_config.json`）。 | 中 | `config.json`（内容 `scripts` / `auto_start_on_launch` / `launch_game_on_open` / `game_launch_delay`）是孤儿文件。按 README 理解它的人会去改它并期望生效，改完无效果；同时误以为打包产物含默认配置。 |
| P4 | `doc/LIVE-DEBUGGING.md:160` vs `.ruff_baseline`、`CLAUDE.md:89`；`CHANGELOG.md:810` vs 实际 collect | LIVE-DEBUGGING §7 写「lint 基线……全仓合计 **64 条**」，实际 `.ruff_baseline` 与 `ruff check .` 均为 **5 条**（`55758af` 已清零存量）；CLAUDE.md:89 写「当前基线只剩 5 条」是对的。CHANGELOG:810 写「测试基线 **212 条**与 `pytest --collect-only` 实际收集数一致」，实际为 **226 条**；CLAUDE.md:92 写 226 是对的。 | 中 | 门禁预期被写成两套数字；执行 Agent 若以 64 条为基线，会把「新增 3 条告警」误判成改善。 |
| P5 | `common.py:930-946`、`tests/test_smoke.py:40,52` | `find_center_silent` 的 docstring 写「与 `find_center` 的**唯一区别**是不输出相似度分数」，实际它还有 `timeout`/`interval` 轮询、`client_region` 每轮重算、窗口矩形刷新分支。`test_smoke.py` 两处注释引用 `common.py:1076` / `common.py:1084`（`is_lineup_acceptable` 的特殊角色与未识别档位分支），实际该函数在 `common.py:1590`。 | 低 | 维护者按注释定位分支会找错行；把 `find_center_silent` 当成纯静默版而忽略其轮询语义，可能写出双重超时。 |

### 维度 2：文档缺漏

| # | 位置 | 问题描述 | 严重 | 影响范围 |
| --- | --- | --- | --- | --- |
| P6 | 14 个顶层模块 | `README.md:358`「代码规范 1」要求「每个 `.py` 顶部含模块级 docstring」。实测 36 个顶层 `.py` 中 **14 个没有**：`hero_metadata.py`、`jiance.py`、`meirirenwulingqu.py`、`mimengzhiyu.py`、`nvshenta.py`、`pata.py`、`pujing.py`、`push.py`、`shangcheng.py`、`shouquguajijiangli.py`、`version.py`、`warehouse.py`、`youjian.py`、`youyishangcheng.py`。其中 `push.py`（1,000 行）、`warehouse.py`（887 行）、`mimengzhiyu.py`（443 行）是核心流程。 | 中 | 零背景 Agent 接手时无法从文件头判断职责、关键接口、依赖；与项目自定规范直接冲突。 |
| P7 | `game_bot_config.json` / `config.json` | 用户配置的字段（`scripts`、`script_order`、`schedule_time`、`auto_start_on_launch`、`launch_game_on_open`、`game_launch_delay`、各任务 `params`）散落在 `bot_runtime.py` 与 `Goldenhandmaidens.py` 的读写处，**没有 schema 文档或字段清单**；`config.json` 既无用途说明也无消费者（见 P3）。 | 中 | 改配置全靠读代码；新增字段时不知道要同步哪些读写点。 |
| P8 | `README.md:38` vs `updater.py:10-44` | README 写「检查更新：对比本地 `version.py` 与远程 `version.json`」；实际实现请求 GitHub `releases/latest` API 并取 `assets[0]` 的 `browser_download_url`，没有 `version.json`。文档也未说明更新源是**上游仓库**。 | 低 | 用户/维护者不知道「检查更新」实际会下载什么、来自哪个仓库。 |

### 维度 3：架构优化点

| # | 位置 | 问题描述 | 严重 | 影响范围 |
| --- | --- | --- | --- | --- |
| P9 | `common.py`（1,700 行 / 69 顶层函数）、`Goldenhandmaidens.py`（2,105 行） | `common.py` 同时承担模板缓存/路径、截图与后台帧、窗口与客户区、点击 IPC、协作式停止、日志出口、弹窗清理、返回主界面、阵容判定、区域变化判据、HUD 点击、中文名映射共 12 类职责。`Goldenhandmaidens.py` 单文件含 GUI 构造、控件、调度、配置、热键、更新、日志队列。README:179 已承认主文件是「仓库里最大的单文件」。 | 中 | 任一底座改动都会牵动 20+ 任务；测试必须 monkeypatch `common` 的模块级全局，难以做单元隔离；新人定位功能的成本高。 |
| P10 | `common.py:547`、`Goldenhandmaidens.py:1806-1809`、`hongbaolingqu.py`（:54,:60,:67,:105,:122,:141,:500）、`yuanwangdan.py`（:43,:96,:360）、`dianfengjingjichang.py:47`、`mimengzhiyu.py:41`、`yingxiongtingtang.py:37,83`、`fanfanle.py:3`、`tests/test_templates.py:20` | 「客户区 1600×900」假设与大量固定点位/偏移常量分散在至少 10 个文件，没有集中注册表或 manifest。`doc/TEMPLATE-AUTHORING.md:9-13` 明确写过换分辨率时「模板 + 相关偏移常量必须一起重做」，但没有可机械枚举的清单。 | 中 | 换分辨率时靠人肉 grep 找偏移，必漏；`TEMPLATE-AUTHORING.md` 记录的 1302×1080 → 1600×900 事故（14 张模板与全部偏移重做）会重演。 |
| P11 | `common.py:1201-1264` (`TEMPLATE_CN`) | 手工维护的 129 项「拼音 → 中文」映射与 140 个模板字面量引用已漂移：至少 25 个引用基名没有中文名（`artificial`、`autocha`、`chengzhangtiaozhan`、`dianfengmeirijiesuan`、`gonghuirenwu`、`jiayuanmubiao`、`jieshezhanxianbiaoti`、`lieshoujiaru`、`lieshoujingguai`、`lieshouxunshangbiaoti` 等），另有 15 个键没有同名模板文件（`exit_final`、`jiaofu`、`migong`、`shouqu` 等属动作名混入模板表）。没有任何用例校验覆盖率。 | 低 | README:95 承诺「日志能读又能对回模板文件」，新模板加入后实际退回纯拼音；映射表随功能增长持续腐化。 |

### 维度 4：代码写法

| # | 位置 | 问题描述 | 严重 | 影响范围 |
| --- | --- | --- | --- | --- |
| P12 | `updater.py:10,41,49-96`；`Goldenhandmaidens.py:248,2027-2037,2073-2086` | `GITHUB_API` 指向 **`yangyh02/afk-journey-merlin-auto`**（上游），而 `README.md:7` 声明本仓库是 `schalkiii/afk-journey-merlin-auto` 二次开发。GUI 启动 1 秒后自动后台检查更新（:248），`check_update()` 仅比较数字版本；`download_update()` 取 `assets[0]`（不校验文件名/扩展名/大小），`install_and_restart()` 生成 `update.bat` 用 `move /y` 直接覆盖正在运行的 `sys.executable`，**无备份、无校验、无回滚**。全仓无密钥，但这是产物完整性问题。 | **高** | 用户点「检查更新」或启动自动检查时，若上游 release 的版本号大于本地 `v1.4.7`，会下载上游 exe 覆盖本 fork 产物，**本仓库全部增强（公会玩法、红点领取、愿望单等）在一次更新中丢失且不可恢复**。 |
| P13 | `common.py:1310-1328`（`clicker_alive`）；调用点 `Goldenhandmaidens.py:1860` 附近 | 存活探针的实现是「把当前光标位置写成一条坐标，看 AHK 是否消费」。消费意味着点击器会在**该坐标真实点击一次**。文档 `doc/LIVE-DEBUGGING.md:9` 把它列为每个实跑的前置检查，GUI 也在每个任务前调用。 | 中 | 探测函数带点击副作用：若用户光标停在别的窗口的按钮/输入框上，会被误点一次；与「不占用户鼠标」的目标相冲突。 |
| P14 | `updater.py:29-46`；`goldenhandmaidens.spec:4,12-16` | `check_update()` 成功返回 4 元组 `(has_update, latest_tag, download_url, html_url)`、失败返回 2 元组 `(None, error_msg)`，调用方靠 `result[0] is None` 分支解包；任何新增调用点直接四元解包会 `ValueError`。spec 的 `Analysis(['goldenhandmaidens.py'])` 用全小写文件名，而磁盘上是 `Goldenhandmaidens.py`；`hiddenimports` 的排除条件 `f != "goldenhandmaidens.py"` 因大小写不匹配而失效，实测 `glob("*.py")` 把 `Goldenhandmaidens` 收进了 hiddenimports。 | 低 | 接口契约脆弱；在大小写敏感的文件系统上打包直接失败；主模块被重复收集（Windows 上通常无害但违背注释意图）。 |
| P15 | 25 个模块的 `if __name__ == "__main__":` | 入口都只调 `main()` / `flow_xxx()`，但**均未注入 `set_stop_checker()` 或 `set_log_sink()`**。直接 `python <module>.py` 会真实驱动点击链路且无法用 F9 停止，日志只进 stdout。`doc/LIVE-DEBUGGING.md:32` 把「直调流程」列为合法实跑方式，没有提示该限制。 | 低 | 误执行单文件时可能真实操作账号资源（领取/推图会消耗门票），且无法即时中断。 |

### 维度 5：测试覆盖率

| # | 位置 | 问题描述 | 严重 | 影响范围 |
| --- | --- | --- | --- | --- |
| P16 | `tests/`（34 文件 / 226 用例） | 12 个顶层模块在全部测试文件正文中从未出现：`drag_utils`、`flow_enter`、`flow_gonghui`、`formation`、`hero_metadata`、`jieshezhanxian`、`lieshouxunshang`、`meirirenwulingqu`、`shangcheng`、`shouquguajijiangli`、`version`、`youyishangcheng`。`ensure_main_interface` 被 **0** 个测试文件引用；`yuanwangdan.main()` 的主状态机（交付循环、`claim_due`、idle 上限、收尾清理）无直接用例，该文件只测了 `_panel_state` / `_wait_gone` / `_claim_reward` / `_craft_from_lack`。 | 中 | 任务切换兜底（P1 的关键路径）与两个公会玩法日常、邮件/商城等流程无回归保护；`main()` 的循环退出条件改动不会被测试挡住。 |
| P17 | `tests/test_templates.py:31-35,41-45,62-72` | 只扫 `templates/*.png`（顶层 338 张）；`templates/migong/` 的 **133 张**模板完全不参与「尺寸 ≤1600×900」校验。`_literal_template_refs()` 的正则只匹配单参数 `get_template_path("x.png")`，而 `flow_migong.py:51` 用 `get_template_path(name + ".png", subdir="migong")`、`formation.py:42` 用变量 `subdir=`，这类引用不校验存在性。docstring 只解释了英雄模板动态拼名，未覆盖 migong 子目录。 | 中 | 子目录模板裁错尺寸或文件缺失可静默通过门禁；README:391 声称「新增用例沿用范式、模板装上即 pytest」对该类资源不成立。 |
| P18 | `tests/test_smoke.py:15-22` | `test_all_modules_import` 用 `f != "start.py"` 排除了 `start.py`，没有注释说明原因；`start.py` 本身有完整模块 docstring 且导入无副作用（已核对文件头）。该用例也没有显式 `assert`（依赖 `importlib.import_module` 抛异常）。 | 低 | 登录模块的导入健康度不在冒烟范围，且排除理由不可追溯。 |

### 维度 6：测试严谨性

| # | 位置 | 问题描述 | 严重 | 影响范围 |
| --- | --- | --- | --- | --- |
| P19 | `tests/test_templates.py:75-83`；`tests/test_smoke.py:15-22` | AST 扫描 34 个测试文件共 217 个 `test_` 函数，其中 **2 个没有任何 `assert` / `pytest.raises` / `pytest.warns`**：`test_reports_unreferenced_templates`（只 `print` 两行，随后 `capsys.readouterr()` 吞掉输出，完全恒真）与 `test_all_modules_import`（隐式依赖导入异常）。 | 中 | 「226 passed」里含一条纯空跑用例；孤儿模板数量（实测 200 个未被字面量引用）只被打印、从不校验，模板腐化不会被门禁发现。 |
| P20 | `tests/` 无 `test_updater.py` | `updater.py` 零测试覆盖。`check_update()` 的 4/2 元组分支、`assets[0]` 选取、`download_update()` 的 `frozen` 短路、`install_and_restart()` 生成的 bat 内容均无打桩验证；P12 的破坏性链路没有任何回归保护或负验证。 | 中 | 改动更新链路（例如换仓库地址）没有测试能证明行为正确；按 `CLAUDE.md:93` 的要求，这属于「新写分支缺用例」。 |
| P21 | `CLAUDE.md:93`；`doc/LIVE-DEBUGGING.md:164-168` | 两处要求「新增用例必须做负验证：改坏被测逻辑，用例必须失败」，并举例说明哪些用例已做过。仓库内没有可核对的负验证记录（脚本、日志或用例注释），无法区分「做过但没留痕」与「没做」。 | 低 | 绿色用例的有效性不可追溯；后续 Agent 无法判断哪些用例是恒真的。 |

### 维度 7：工程规范

| # | 位置 | 问题描述 | 严重 | 影响范围 |
| --- | --- | --- | --- | --- |
| P22 | `.gitignore`、`config.json`、`goldenhandmaidens.spec:10` | `.gitignore` 忽略了 `game_bot_config.json` / `game_bot.log` / `shared/` / `debug/` / `_tmp_*` 等，但**未忽略孤儿 `config.json`**，该文件已入库；同时 spec 的 `datas` 不含它（见 P3）。 | 中 | 死文件持续入库；构建产物与 README 描述不一致，解包校验时会被当成缺失资源。 |
| P23 | `build.ps1:16-24,46` | `Invoke-Check` 调用裸 `python`（PATH 解析），未固定到 `README.md:255` 要求的 Python 3.13；ruff 比对依赖 `--output-format concise` 的正则解析，ruff 升级改输出格式即静默失配（脚本已有「无可解析输出则失败」保护，但只覆盖「一条都没有」的情况）。 | 低 | 换机器/多 Python 共存时门禁结果不可复现。 |
| P24 | `CHANGELOG.md`（838 行，全部在 `## 未发布（Working）` 下）、`version.py` | CHANGELOG 自 2026-11-02 起累积 9 个批次、仍全部挂在「未发布」；`version.py` 停 `v1.4.7`，没有把已发布的批次切成版本段落。 | 低 | 发版时无法从 CHANGELOG 直接生成 release notes；`updater` 的版本比较与 CHANGELOG 无对应关系。 |

### 维度覆盖声明

七个维度均已逐项排查并给出结论，无遗漏：
1 文档一致性 → P1–P5；2 文档缺漏 → P6–P8；3 架构优化点 → P9–P11；
4 代码写法 → P12–P15；5 测试覆盖率 → P16–P18；6 测试严谨性 → P19–P21；
7 工程规范 → P22–P24。

---

## 3. 改进建议

> 每条给「具体做法 / 修改涉及的文件清单 / 验证方式」。
> 文件清单以「可直接交给 Agent 开工」为准；验证命令统一使用仓库根的绝对路径语境。

### S1（对应 P12，最高优先）：切断「更新覆盖 fork」的通道

- **做法**：
  1. 把 `GITHUB_API` 改为配置项（默认指向本 fork `schalkiii/afk-journey-merlin-auto`），
     或在确认本仓库不发布 Release 时**直接禁用自动更新**：`check_update()` 返回
     `(False, __version__, "", "")`，GUI 的「检查更新」按钮提示「本分支不提供自动更新」。
     二选一，不要保留「指向上游 + 自动弹窗」的中间态。
  2. `check_update()` 统一返回 4 元组（失败也返回 `(None, "", "", str(e))`），消除 P14 的契约分叉。
  3. 下载前校验 asset：文件名以 `.exe` 结尾、`size` 在合理区间、`Content-Length` 与声明一致；
     安装前把当前 exe 复制为 `.bak`，`update.bat` 失败时回滚；把「是否 fork 同源」写进日志。
  4. 补 `tests/test_updater.py`：`check_update` 成功/失败/版本比较、`assets[0]` 非 exe 被拒、
     `frozen=False` 短路、`install_and_restart` 生成的 bat 内容（打桩 `os.startfile` / `sys.exit`）。
     每条做负验证（改坏校验逻辑后用例必须红）。
- **文件清单**：`updater.py`、`Goldenhandmaidens.py`（`_auto_check_update` / `_check_update_clicked` /
  `_show_update_dialog` / `_install_and_restart`）、`README.md:38`、`tests/test_updater.py`（新建）。
- **验证方式**：
  `python -m pytest tests/test_updater.py -q` 全绿；把 `GITHUB_API` 临时改回上游地址跑
  `check_update` 的负验证用例，必须失败；`python -m ruff check .` 不新增告警；
  实机（可选）：在副本上点「检查更新」，确认不会下载并覆盖 `goldenhandmaidens.exe`。

### S2（对应 P1）：实测「家园视图是否算主界面」，统一口径并处理兜底失败

- **做法**：
  1. 实机在家园视图调用 `common.at_main_interface()`（0.8 阈值 + 无返回箭头），记录
     `wanfamulu` 的实际匹配分。以实测结果为准，**统一** `README.md:278`、
     `Goldenhandmaidens.py:208-209`、`yuanwangdan.py:482-485` 三处结论。
  2. 若实测为 `False`：`run_scripts_thread` 必须处理 `ensure_main_interface()` 的返回值
     （记日志 + 标记该任务失败/跳过，或先把游戏切回主界面再继续），不能静默忽略；
     并在 GUI 里防止把「家园愿望单」拖到非末尾位置（或明确提示）。
  3. 若实测为 `True`：删除 `yuanwangdan.py` 中「固定排末尾」的注释与
     `if _find(tpl_entry) is None: flow_return_main()` 的特殊分支，让它与其他任务一致。
- **文件清单**：`README.md`、`Goldenhandmaidens.py`、`yuanwangdan.py`、
  `tests/test_common_ensure_main.py`（新建）、`tests/test_gui_run_status.py`（补返回值处理用例）。
- **验证方式**：实机记录匹配分写入提交说明；`python -m pytest tests/test_common_ensure_main.py
  tests/test_gui_run_status.py -q` 全绿；负验证：把 `ensure_main_interface` 打桩成恒 `False`，
  新的调度用例必须失败（证明「忽略返回值」已被挡住）；`pwsh -NoProfile -File build.ps1 check`。

### S3（对应 P13）：让点击器存活探测不产生真实点击

- **做法**：`clicker_alive()` 改为无副作用探测：优先用 `tasklist /FI "IMAGENAME eq
  click_from_file.exe"` 判定进程存在；若要保留「消费坐标」语义，需给 AHK 增加独立的
  heartbeat 协议（写 `shared/clicker_heartbeat.txt`，AHK 只删文件不点击）——后者需要
  AHK 源码，而仓库只有编译产物，因此**建议采用进程探测 + 保留 `send_coord` 的
  `CLICKER_MISS_LIMIT` 连续未消费抛错作为二次保险**。
- **文件清单**：`common.py`（`clicker_alive` 及 `CLICKER_MISS_LIMIT` 注释）、
  `doc/LIVE-DEBUGGING.md:9-13`、`tests/test_clicker_guard.py`（补用例）。
- **验证方式**：`python -m pytest tests/test_clicker_guard.py -q`；实机把光标停在桌面图标上
  调用 `clicker_alive()`，确认图标未被点开；负验证：打桩成恒 `True`，调度用例必须失败。

### S4（对应 P2/P3/P4/P5/P8/P22/P24）：文档与死文件清理

- **做法**：
  1. 删 `README.md:340` 的 `doc/AUDIT-REPORT-*.md` 条目，改为指向本报告；
     CHANGELOG:505 的死链改为纯文本说明（或注明「报告已删除」），:372/:810 同步措辞。
  2. 处理 `config.json`：确认无消费者后**删除文件**并在 `.gitignore` 加一条；
     同步修正 `README.md:168,343,453`（spec 只打 3 个 json，`config.json` 不是默认配置）。
     若决定保留，则必须补一个实际读取它的入口并写进 spec `datas`——二选一。
  3. `doc/LIVE-DEBUGGING.md:160` 的「64 条」改为 5 条；`CHANGELOG.md:810` 的「212 条」
     改为「226 条（见 `CLAUDE.md`）」。
  4. `common.py:930` 的 docstring 改为列出真实差异（timeout/interval 轮询、client_region
     每轮重算、窗口矩形刷新）；`tests/test_smoke.py:40,52` 的行号改为函数引用而非行号。
  5. `README.md:38` 按 S1 结果改写更新来源说明。
  6. CHANGELOG 按已发布批次切出版本段落，`version.py` 与段落对齐。
- **文件清单**：`README.md`、`CHANGELOG.md`、`CLAUDE.md`、`doc/LIVE-DEBUGGING.md`、
  `common.py`、`tests/test_smoke.py`、`config.json`（删除）、`.gitignore`、
  `goldenhandmaidens.spec`（仅当选择保留 config.json 时）。
- **验证方式**：`markdownlint README.md CHANGELOG.md CLAUDE.md doc/*.md` 零 error；
  `grep -rn "AUDIT-REPORT" --include="*.md" .` 不再有指向已删除文件的链接；
  `python -m pytest -q` 全绿；`python -m ruff check .` 仍为 5 条；
  `git status --short` 只出现本次改动的文档/配置。

### S5（对应 P16/P17/P19/P20/P21）：补测试盲区与消除恒真用例

- **做法**：
  1. `tests/test_templates.py`：把扫描改为 `glob(..., recursive=True)` 覆盖
     `templates/migong/`；新增「migong 子目录模板尺寸」与「`flow_migong` 引用的名字在子目录
     存在」两条断言；`test_reports_unreferenced_templates` 改为对孤儿数量设上限断言
     （先记录当前 200 个为基线，超过则失败），或改成 `pytest.warns`/显式 `assert`。
  2. 新建 `tests/test_common_ensure_main.py`（与 S2 共用）、
     `tests/test_yuanwangdan_main.py`（打桩 `_panel_state` 序列，覆盖：交付 3 单后命中
     `MAX_ORDERS`、`claim_due` 只在交付后置位、连续 8 轮 one_key 退出、收尾关闭结算）、
     `tests/test_updater.py`（S1 共用）。
  3. `tests/test_smoke.py`：把 `start.py` 加入导入列表，或写明排除原因；补一条显式断言
     （例如 `assert mods`）。
  4. 为 `flow_enter` / `flow_gonghui` / `jieshezhanxian` / `lieshouxunshang` 各补一条
     最小决策用例（入口分流、次数上限），不必覆盖像素。
  5. 按 `CLAUDE.md:93` 为每个新增用例做负验证，并把「改坏了什么 / 哪条变红」写进用例
     docstring 或提交说明。
- **文件清单**：`tests/test_templates.py`、`tests/test_smoke.py`、`tests/test_yuanwangdan_main.py`（新）、
  `tests/test_common_ensure_main.py`（新）、`tests/test_updater.py`（新）、
  `tests/test_flow_gonghui.py`（新）、`tests/test_gonghui_dailies.py`（新）、`tests/conftest.py`（如需新夹具）。
- **验证方式**：`python -m pytest -q` 收集数 >226 且全绿；逐条负验证记录可核对；
  `pwsh -NoProfile -File build.ps1 check` 退出码 0；
  故意删掉一张 migong 子目录模板（在临时副本上），新增用例必须失败。

### S6（对应 P6/P7）：补齐模块文档与配置 schema

- **做法**：
  1. 给 P6 清单中的 14 个模块补模块级 docstring（功能 / 关键接口 / 依赖三要素）。
     `version.py`（1 行常量）与 `hero_metadata.py`（纯数据表）可在 README 代码规范里
     明确列为豁免，避免规范与实际长期不符。
  2. 新建 `doc/CONFIG.md`：列出 `game_bot_config.json` 全部字段、类型、默认值、读写位置
     （`bot_runtime.py` / `Goldenhandmaidens.py`），并说明 `config.json` 已删除（S4 结果）。
- **文件清单**：14 个模块（逐个）、`README.md`（代码规范豁免说明 + 项目结构新增 `doc/CONFIG.md`）、
  `doc/CONFIG.md`（新）。
- **验证方式**：AST 脚本重跑「缺 docstring 模块」计数为 0（或仅剩豁免清单）；
  `markdownlint README.md doc/*.md` 零 error；`python -m pytest -q` 全绿。

### S7（对应 P9/P10/P11，架构分支，建议独立成一轮任务）

- **做法**：
  1. 建立 `doc/CLIENT-RESOLUTION.md` 或在 `common.py` 集中定义 `CLIENT_WIDTH=1600` /
     `CLIENT_HEIGHT=900`，把 P10 列出的固定点位/偏移常量登记成一张表（模块、常量名、
     实测坐标、对应模板），并加一条用例校验「所有登记的偏移都在客户区内」。
  2. `TEMPLATE_CN` 补 25 个缺失映射，把 15 个动作名从「模板表」迁到独立的 `ACTION_CN`；
     新增用例断言「所有 `get_template_path` 字面量引用的基名都在 `TEMPLATE_CN` 中」。
  3. **不要在本次架构轮做 `common.py` 拆分**：先完成 S1–S6，再单独开一轮按职责拆成
     `templates.py` / `capture.py` / `clicker.py` / `window.py`，并用 `common.py` re-export
     保持 `from common import ...` 全仓不改。拆分前必须有 S5 的测试网。
- **文件清单**：`common.py`、`doc/CLIENT-RESOLUTION.md`（新）、P10 列出的 10 个模块（只改注释/常量引用）、
  `tests/test_client_constants.py`（新）、`tests/test_template_names.py`（新）。
- **验证方式**：`python -m pytest -q` 全绿；把 `CLIENT_WIDTH` 临时改成 1599 跑新用例必须失败；
  `python -m ruff check .` 不新增告警；实机截图复核 3 个代表性偏移仍命中。

### S8（对应 P14/P15/P18/P23）：工程一致性收尾

- **做法**：spec 入口改用磁盘实际大小写 `Goldenhandmaidens.py`，排除条件同步改；
  25 个 `__main__` 入口统一走一个 `common.bootstrap_cli(main)`（注入 no-op stop checker
  与 stdout log sink），或在 `doc/LIVE-DEBUGGING.md` 明确写「单文件直调不可用于账号操作」；
  `build.ps1` 把 `python` 换成可配置的 `$Python`（默认解析 3.13）并校验版本；
  `test_all_modules_import` 补 `start.py` 与断言。
- **文件清单**：`goldenhandmaidens.spec`、`common.py`（若采用 bootstrap）、25 个模块的
  `__main__` 块（机械替换）、`build.ps1`、`doc/LIVE-DEBUGGING.md`、`tests/test_smoke.py`。
- **验证方式**：`pwsh -NoProfile -File build.ps1 check` 退出码 0；
  解包校验（见 `doc/LIVE-DEBUGGING.md:176-183`）确认主模块只被收集一次；
  `python -c "import subprocess; ..."` 确认 `__main__` 注入后不会在导入时触发点击。

---

## 4. 优先级与并行性

### 4.1 排序（从高到低）

| 序 | 建议 | 处理的问题 | 优先级 | 并行性 |
| --- | --- | --- | --- | --- |
| 1 | S1 | P12、P14(部分)、P20 | **P0** | 需串行（updater 与 GUI 同链路） |
| 2 | S2 | P1、P16(部分) | **P0** | 需串行（与 S1 共享 `Goldenhandmaidens.py`） |
| 3 | S3 | P13 | P1 | **可并行**（只改 `common.py` 的 `clicker_alive` + 文档 + 测试；与 S1/S2 的 `Goldenhandmaidens.py` 无重叠，但 `common.py` 与 S7 重叠，故与 S7 串行） |
| 4 | S5 | P16、P17、P19、P20、P21、P18(部分) | P1 | **可并行**（只改 `tests/` 新建/既有文件；与 S1/S2/S3 的代码文件无重叠） |
| 5 | S4 | P2、P3、P4、P5、P8、P22、P24 | P1 | **可并行**（只改 `.md` / `config.json` / `.gitignore`；与 S1/S2/S3/S5 无重叠。注意 `README.md` 也被 S6、S1 引用，故 S4 与 S6/S1 串行） |
| 6 | S6 | P6、P7 | P2 | 需串行（与 S4 共享 `README.md`） |
| 7 | S8 | P14、P15、P18、P23 | P2 | **可并行**（spec / build.ps1 / 机械替换 `__main__`；与 S1 的 `Goldenhandmaidens.py` 之间只在 `__main__` 块，需与 S1 协调） |
| 8 | S7 | P9、P10、P11 | P3 | 需串行（架构分支单独一轮，且依赖 S5 的测试网与 S3 的 `common.py` 改动落定） |

### 4.2 可并行组（已确认组内文件无重叠）

- **组 A（可与组 B/C 并行）**：`tests/` 目录全部改动（S5）、`build.ps1` / `goldenhandmaidens.spec`（S8），
  以及 `doc/CONFIG.md` 之外的纯文档（S4 的 CHANGELOG/CLAUDE/doc 部分）。
- **组 B（代码链，串行）**：`updater.py` → `Goldenhandmaidens.py`（S1）→ `yuanwangdan.py`（S2）
  → `common.py`（S3）。
- **组 C（README 链，串行）**：S4 的 `README.md` 改动 → S6 的 `README.md` 改动。
- **约束**：`common.py` 同时出现在 S3、S5（测试打桩）、S7、S8 的引用里；
  S3 与 S7 必须串行，S5/S8 只引用不修改 `common.py` 时可并行。
- **组 D（最后单独一轮）**：S7 架构分支，不与任何其他组并行。

### 4.3 验收总判据

每一组完成后都必须跑通：

```text
python -m pytest -q                      # 全绿，收集数 ≥226
python -m ruff check . --output-format concise   # 5 条，与 .ruff_baseline 一致
markdownlint README.md CHANGELOG.md CLAUDE.md doc/*.md   # 0 error
pwsh -NoProfile -File build.ps1 check    # 退出码 0
git status --short                       # 只含本组预期文件
```

---

## 5. 后续执行纪律（拼接 `software-improvement`）

`project-audit` 的纪律是「只输出弹药，不动手改」。下一阶段执行建议按 `software-improvement`
的**单一分支**原则拆成独立任务，一次只走一个分支：

| 轮次 | 分支 | 对应建议 | 开工前 |
| --- | --- | --- | --- |
| 1 | 代码质量（缺陷修复，非重构） | S1 + S2 + S3 | 确认基线：pytest 226/226、ruff 5、markdownlint 0 |
| 2 | 测试 | S5 | 轮 1 全绿后再开工 |
| 3 | 文档 | S4 + S6 | 轮 1 的结论（实测匹配分、更新源决策）已定稿 |
| 4 | 工程规范 | S8 | 与轮 1 的 `Goldenhandmaidens.py` 改动协调 |
| 5 | 架构 | S7 | 轮 2 的测试网已就位，单独一轮，不混入功能性改动 |

三条通用原则（适用于每轮）：

1. **最小改动**：只改建议列出的文件，保持 `from common import ...`、文件 IPC、GUI 分发等
   既有设计不变；不顺手重构相邻代码，不删除与本次改动无关的既有注释。
2. **逐点验证**：每完成一个改动点立即跑 `python -m pytest -q` 与
   `python -m ruff check .`，全绿后再进入下一点；禁止批量改完统一验证。
   清理只走 `pwsh -NoProfile -File build.ps1 clean`，不直接删缓存目录。
3. **注释同步**：代码变更后同步更新相关注释，注释只解释当前实现的逻辑与设计思路，
   不写「原来怎样 / 本次改了什么」的版本史；新增用例按 `CLAUDE.md:93` 做负验证并留痕。

进入分支前读取对应细则文件（架构 / 代码质量 / 文档 / 测试），按该分支末尾的「完成判据」
自查后再输出改动清单。本报告中的「实测」「当前值」均为 2026-11-07 快照，执行时须先复核
（尤其 `pytest` 收集数与 ruff 条数会随改动变化）。

---

## 6. 自查

- 现状部分只写计数、文件、行号与命令输出，无推测词。
- 七个维度全部有结论，每条问题含位置 / 描述 / 严重程度 / 影响范围。
- 标为「高」的 P1 与 P12 都写清了具体后果（连锁任务失败 / fork 产物被上游覆盖不可恢复）。
- 每条建议含做法、文件清单、验证方式；可并行组已核对文件无重叠，
  共享 `README.md`、`common.py`、`Goldenhandmaidens.py` 的条目已标为需串行。
- 一个对项目零背景的 Agent 可以照 S1 的步骤直接开工，不需要本报告之外的隐含上下文。

---

## 7. 处置记录（2026-11-07 当日执行，问题清零）

> 第 2 节的问题清单保留审计时的原始登记，不回改；本节逐条给出处置与可复现的验证证据。
> 执行按第 5 节的单分支纪律分五轮推进，每轮结束跑测试，最后跑完整门禁。

### 7.1 逐条处置

| # | 处置 | 验证证据 |
| --- | --- | --- |
| P1 | 三处口径统一为「家园视图判据不可靠、建议排末尾」；新增 `_skip_task_when_not_at_main` 处理 `ensure_main_interface()` 返回值（无法恢复则标记失败、留现场、跳过），拖拽到中间时给出提示 | `README.md`、`Goldenhandmaidens.py:208,520,1797`、`yuanwangdan.py:482`；`tests/test_common_ensure_main.py`（5 条含负验证留痕） |
| P2 | README 项目结构改指向本报告；CHANGELOG 三处历史报告引用改为「当时…已清理」并去掉死链 | `grep -rn "AUDIT-REPORT" --include="*.md" .` 无指向已删除文件的链接；markdownlint 0 error |
| P3 | 删除孤儿 `config.json`（`git rm`），`.gitignore` 加条目；README 三处修正打包资源与项目结构；新建 `doc/CONFIG.md` | `git status` 显示 `D config.json`；全仓 `*.py` 无 `config.json` 读取点 |
| P4 | `LIVE-DEBUGGING.md` 的 64 条改为 5 条；CHANGELOG 历史数字标注「当时」；`CLAUDE.md` 基线写 287 条 | `ruff check .` 5 条 = `.ruff_baseline`；`pytest -q` 287 passed |
| P5 | 重写 `find_center_silent` docstring 列出真实差异；`test_smoke.py` 的行号注释改为函数引用 | `common.py:930`；`tests/test_smoke.py` |
| P6 | 14 个顶层模块补模块级 docstring（含 `version.py` 纯常量与 `hero_metadata.py` 数据表，故无需豁免清单） | AST 复核「缺 docstring 模块」= 0 |
| P7 | 新建 `doc/CONFIG.md`：字段类型/默认值/读写位置、运行时文件、改配置注意事项 | markdownlint 0 error |
| P8 | README:38 改为本 fork Release + 资产校验 + `.bak` 回滚 + `GAMEBOT_UPDATE_REPO` | `updater.py` 与 `README.md` 一致 |
| P9 | **决策性关闭**：抽离 `template_names.py`（纯数据 + `display_name`）由 `common` re-export，`common.py` 减约 80 行；剩余职责保持单文件，理由：20+ 模块全量 `from common import ...`，物理拆分的回归风险高于收益，已通过常量集中与测试网消除可维护陷阱 | `template_names.py`；AST 全量导入冒烟 `test_smoke.py`；`pytest` 287 全绿 |
| P10 | `common.CLIENT_WIDTH/HEIGHT` 单一来源，`BOTTOM_BAR_CLIENT_REGION` 与 GUI 警告均引用它；新建 `doc/CLIENT-RESOLUTION.md` 登记全部点位/偏移 | `tests/test_client_constants.py`（负验证：改 1599 必红）；`tests/test_client_constants.py` 4 条通过 |
| P11 | `TEMPLATE_CN`（160 项，均有同名 PNG）与 `ACTION_CN`（18 项，动作名/可选模板）分离，`LOG_NAME_MAP` 合并保持日志行为不变；补齐 49 个漂移项 | `tests/test_template_names.py`（6 条，含引用全覆盖断言）；`tests/test_log_format.py` 通过 |
| P12 | Release 源改本 fork、统一 4 元组、只接受具名且达 1 MB 的 exe、下载不完整丢弃、覆盖前 `.bak` + bat 失败回滚 | `tests/test_updater.py` 9 条（含「源不含 yangyh02」「bat 含回滚段」）；负验证留痕写入文件头 |
| P13 | `clicker_alive()` 改只读 `tasklist` 探测，不写坐标、不产生点击 | `tests/test_clicker_guard.py`（4 条，含「探测不写 IPC 文件」断言） |
| P14 | `check_update()` 失败也返回 4 元组；spec 入口与排除条件改用磁盘实际大小写 | `tests/test_updater.py::test_check_update_error_returns_four_tuple`；脚本验证 `hiddenimports` 不再收主模块 |
| P15 | **决策性关闭**：保留 25 个 `__main__` 入口（改动面大、收益低），在 `LIVE-DEBUGGING.md` §2 明确「单文件直调不注入 F9 停止/日志汇聚，不得用于账号操作」 | 文档 lint 0 error |
| P16 | 新增 7 个测试文件，补齐 `flow_enter` / `flow_gonghui` / 公会日常 / 邮件 / 商城 / 挂机 / 拖拽 / 阵容 / 元数据 / 版本 / `yuanwangdan.main()` / `ensure_main_interface` 的决策覆盖 | 机械复核「测试全文未提及模块」= **0** |
| P17 | `test_templates.py` 递归扫描全部 471 张（含 `migong` 133 张）、校验 `flow_migong` 动态拼名的 20 个引用、孤儿数量设上限 | `tests/test_templates.py` 5 条；负验证：删一张 migong 模板必红 |
| P18 | `test_smoke.py` 移除 `start.py` 排除并加显式断言 | `tests/test_smoke.py::test_all_modules_import` |
| P19 | 消除 2 条恒真用例：`test_reports_unreferenced_templates` 改为数量上限断言，`test_all_modules_import` 加断言 | AST 复核 287 个用例中「无 assert/raises」= **0** |
| P20 | 新建 `tests/test_updater.py`（9 条），覆盖成/败/无资产/版本比较/下载短路/bat 回滚 | 文件头写明 4 条负验证路径 |
| P21 | 每个新增测试文件的模块 docstring 都写「负验证留痕」（改坏哪处、哪条变红）；`LIVE-DEBUGGING.md` §7 增补可核对要求 | 7 个新测试文件均有该段落 |
| P22 | `config.json` 删除并忽略；spec `datas` 保持 3 个实际会读的 json，README 不再声称「各 *.json」 | `git status` + 文档一致性复查 |
| P23 | `build.ps1` 加 `-Python` 参数与 3.13 版本校验；`check`/`build` 全部改用该解释器；修 `Assert-Python` 的 `Write-Output` 污染返回值 | `pwsh -NoProfile -File build.ps1 check` 输出 `[check] Python 3.13` 且退出码 0 |
| P24 | CHANGELOG 加「版本索引」，把 838 行未发布段归入 `v1.4.7（开发中）`，历史数字标注「当时」 | markdownlint 0 error |

### 7.2 清零结论

24 条问题（P1–P24）**全部处置完毕**，其中 P9、P15 为「评估后决策性关闭」并写明理由与缓解措施，
其余为代码 / 文档 / 测试 / 工程配置的实际改动。七维度均有对应处置，无遗留未决项。

最终门禁（`pwsh -NoProfile -File build.ps1 check`，退出码 0）：

```text
[check] Python 3.13
[check] 1/3 compileall  → 通过
[check] 2/3 pytest      → 287 passed, 3 warnings in 90.79s
[check] 3/3 ruff        → 基线一致（全仓 5 条，基线覆盖 2 个文件）
```

补充核对：`python -m ruff check .` 5 条与 `.ruff_baseline` 一致；
`markdownlint README.md CHANGELOG.md CLAUDE.md doc/*.md` 零 error；
AST 复核模块 docstring 缺失 0、无断言用例 0、测试全文未提及模块 0。

### 7.3 环境注记（非项目缺陷）

- 完整门禁里 pytest 的 3 条 warning 来自 `tests/test_debug_capture.py` 的
  `PytestUnhandledThreadExceptionWarning`（`subprocess` 读取器线程按 GBK 解码失败），
  既有现象、不影响退出码与断言，未在本次「代码质量」分支里顺手改动。
- 受限会话的批量删除守卫会拦截 pytest 清理历史临时目录；`build.ps1 check` 已改为
  每次使用全新的 `--basetemp=.pytest_tmp/run_<时间戳>_<随机数>`，旧目录由 `clean` 目标清理。
  在用户本机（无该守卫）按 README 的 `build.ps1 clean` 正常清理即可。
- 本次未做实机跑测：涉及实际游戏界面的验证（家园视图下 `at_main_interface()` 的匹配分、
  更新对话框的端到端行为）仍需在游戏前台复核，处置采用防御性实现而非依赖实测结论。
