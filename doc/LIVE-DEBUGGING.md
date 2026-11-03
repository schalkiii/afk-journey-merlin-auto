# 实机开发与调试方法学

本文只讲**怎么在这个项目上开发、调试、验证**：怎么在不动用户鼠标的前提下跑真实游戏、
怎么判定「真的进去了 / 真的领到了」、怎么收尾。模板本身的采集与标定规则见
[TEMPLATE-AUTHORING.md](TEMPLATE-AUTHORING.md)；行为约束见根目录 `CLAUDE.md`。

## 1. 前置条件（先确认，否则所有现象都会误诊）

- **点击器存活**：`common.clicker_alive()`。游戏《剑与远征：启程》以**管理员**运行，
  未提权进程的 `SendInput` / `PostMessage` / `PrintWindow` 会被 UIPI 拦截（实测
  PrintWindow ok=0、PostMessage=0）。点击走文件 IPC：Python 写
  `shared/target_coord.txt`（**整屏绝对坐标**）→ 提权的 `click_from_file.exe` 消费并注入。
  点击器自己退出后所有点击静默落空，表现是「界面连续多轮无变化」——先查它，再查逻辑。
- **截图通路**：默认 Windows Graphics Capture（`windows-capture`），能截被遮挡/提权窗口；
  不可用时回退普通屏幕截图。截图坐标系始终是**全屏**，`find_center*` 返回值也是全屏坐标。
- **客户区必须 1600×900**：`game_client_region()` 每次调用都重新校验；不是这个尺寸
  整套模板与偏移全部失效，GUI 启动任务时会打警告。RDP 断连/锁屏时系统停止渲染，
  后台截图拿不到新帧——保持会话连接。

## 2. 怎么发起一次实跑（不碰用户鼠标）

用户明确不要用桌面自动化挪鼠标，所以实跑一律走进程，两种形态：

1. **走 GUI（验证真实用户路径）**：临时脚本实例化 `GameBotGUI` →
   `select_script(idx)` → `root.after(2500, app.run_single_script)` →
   `root.after(120, app._drain_log_queue)` → `mainloop()`。
2. **直调流程（验证单个状态机）**：临时脚本 `import flow_push; flow_push.main(...)`。

共同纪律：

- 用 `pwsh -NoProfile -Command "Start-Process ... -PassThru | Select-Object -ExpandProperty Id"`
  **分离启动并拿 PID**，不要在前台阻塞等待。
- runner 里把 stdout/stderr tee 到 `%TEMP%` 的日志文件并**每行 flush**，
  之后用短命令轮询 `tail -c`；不要 `sleep` 很久再一次性读。
- 结束用 `taskkill //F //PID <pid> //T`（连子进程树），并确认没有孤儿 `python` 留下。
  判别归属看进程 `StartTime`：本轮的 PID 与用户长期存在的进程要分得清。
- 临时脚本与截图**写在 `%TEMP%`，不落在仓库根目录**；用完即删。

## 3. 坐标纪律

- `send_coord` / `click_position` 收的是**整屏绝对坐标**。调试脚本若按客户区坐标点
  （如 `x=100, y=35`）必须加 `game_client_region()` 原点再传，否则点到别处——
  本轮就因这个 bug 把「点击没生效」误判成游戏问题。
- 客户区固定 1600×900 时，允许「固定点位点击」，但**必须带进入校验**（见 §4），
  且把点位写成带注释的常量（如 `LAUREL_HUD_POS = (1550, 610)`），不要散落魔法数。

## 4. 每次点击都要「点 → 校验 → 必要时补点」

- 游戏不在前台时，系统会把**第一次点击用于激活窗口而吞掉**。`ensure_game_clickable`
  先激活，且激活后必须 `sleep(0.25)`——激活是异步的，不等就写坐标仍会被吞（实测复现）。
- 跳转类按钮（玩法目录入口、模式入口、`repeat(e)`、结果页返回）点击后**必须确认目标界面**：
  确认不到时，只在「仍停在原页面」的前提下补点一次；界面已经变化就**不要盲点**。
  参考 `push._enter_mode_and_confirm` / `push._click_repeat_and_confirm`。
- 「已进入某面板」的判据可靠性排序：
  1. 面板内**静态**锚点（不随子页/动画变的控件）；
  2. 对**多个未选中态**页签做或判断（面板会记住上次子页，选中态会换外观）；
  3. 上级判据：「主界面 HUD 是否消失」（`_is_at_main_interface`）。
  不要拿单个页签当唯一锚点，也不要拿半透明 HUD 文字标签当锚点。
- 领取类动作只认**结果信号**：弹出「获得奖励」/「点击空白处关闭」才算领到。
  点了没弹奖励就记入 dead_ends 不再重复点，否则会原地打转。

## 5. 检测器要用正样本验证，不能只看「0 命中」

「扫不到 = 干净」是最容易骗过自己的结论。本轮通用角标检测就是被这条推翻的：
同一屏肉眼有 5 个礼包角标，检测器返回 0。任何「找东西」的函数上线前，先在
**已知存在目标的那一屏**跑一次，断言它能命中并给出坐标；再做负样本（易混淆界面）。

同理，实跑结论要落到可核对的证据行：日志里的
「点击 repeat(e)(1) 后失败页仍在，重试点击 repeat(e)」比「已修复」有用。

## 6. 勘察未知界面的闭环

1. 单击候选位置 → 截图客户区 → 读图确认这是什么界面；
2. 需要新模板时：`crop` 到控件主体 → 在目标屏验证 ≥0.95、在最易混淆屏 ≤0.7、实点确认落点；
3. 模板装进 `templates/` 后立即 `pytest`（`tests/test_templates.py` 会校验所有
   `get_template_path("x.png")` 字面量引用的文件都存在）；
4. 弃用的模板**同时删文件**，不留孤儿（`CLAUDE.md` §3：自己改动产生的孤儿自己清）。

## 7. 门禁与「零新增」基线比对

- 每轮改动：`python -m compileall -q <files>` → `pytest -q` → `ruff check`。
- 本仓 ruff 有既有基线（约 64 条）。判断「有没有引入新问题」不能只看总数，
  要逐文件与 HEAD 比：
  `git show HEAD:push.py | ruff check --stdin-filename push.py --output-format concise -`
- 测试要覆盖**新写的分支**而不是只跑通主路径：吞点击重试、离开原页面后不盲点、
  领取上限截断，都各有一条确定性单测（`tests/test_push_fail_limit.py`、
  `tests/test_hongbaolingqu.py`）。

## 8. 发布收尾链（顺序不能换）

1. 文档同步（README 功能表 / 项目结构、CHANGELOG 记结论与**撤销过的方案**）；
2. `git commit` → `GIT_TERMINAL_PROMPT=0 git -c credential.interactive=false push origin main`
   （本机 GCM 会卡 push，必须非交互）；
3. `python -m PyInstaller goldenhandmaidens.spec --distpath . --workpath build --noconfirm`；
4. **解包校验产物**，不要只看构建成功：
   ```python
   from PyInstaller.archive.readers import CArchiveReader
   a = CArchiveReader('goldenhandmaidens.exe')
   z = a.open_embedded_archive('PYZ.pyz')          # 模块是否打进去（函数内动态 import 也在）
   png = {n for n in a.toc if n.endswith('.png')}   # 模板路径是反斜杠 templates\xxx.png
   ```
5. 清 `%TEMP%` 会话残留 → `git status` 干净 → 把游戏带回主界面（若用户没关游戏）。

## 9. 副作用与账号成本（跑之前要意识到）

- 领取/推图会**真实消耗账号资源**（门票、扫荡次数、派遣），且不可回退。
- 盲点固定坐标可能误闯带**自动派遣倒计时**的活动页（实测误入「纷战争锋」），
  或触发生产/购买。任何「按栅格逐点」的写法都要先想清楚点空位会落到什么控件上。
- 流程末尾必须 `recover_to_main_interface()`，否则下一个任务从错误界面开始，
  表现成「上一任务把下一任务带崩」的假象。
- 日志文件 `game_bot.log` 由独立进程按 **GBK** 写入，读取时按 gbk 解码，否则乱码。
