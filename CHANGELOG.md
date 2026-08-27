# CHANGELOG

## 未发布（Working）

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
