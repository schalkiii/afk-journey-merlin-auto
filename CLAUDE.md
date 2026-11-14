# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```text
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Self-Review After Completion

**Re-read your diff before reporting done. Look for one class of bug per pass.**

After implementing, take 30 seconds to scan the diff with a specific lens each time. Rotate through:

- **Environment split:** Works in frozen EXE? Works in dev mode? Different OS?
- **Edge cases:** Empty input, first run, no network, file locked, no permission.
- **Dead weight:** Parameters imported but unused, variables assigned but never read, code paths that can't be reached.
- **Thread safety:** Shared state between background threads and UI thread.

Don't checklist all four every time — pick the one most relevant to the change. The goal is catching the `python.exe` replacement bug *before* the user asks.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, clarifying questions come before implementation rather than after mistakes, and self-review catches issues before the user does.

## 项目速览

- 一句话：AFK Journey（剑与远征：启程）日常任务自动化 —— tkinter GUI + 模板匹配点击 + 坐标注入器，
  成品是 Windows 单文件 GUI exe（无控制台）。
- 跑起来：源码 `python Goldenhandmaidens.py`；实机自动化需**管理员**权限、游戏窗口标题含
  「剑与远征：启程」、客户区 1600×900。用法与功能表见 `README.md`。
- 门禁 / 打包见下一节；界面结构与视觉规范见 `doc/GUI.md`，实机方法学见 `doc/LIVE-DEBUGGING.md`。

## 项目专属门禁

- 提交前必须跑 `pwsh -NoProfile -File build.ps1 check`（`powershell` 亦可，脚本带 UTF-8 BOM；
  compileall + pytest + ruff 基线比对，退出码 0 才算通过）。
- lint 基线见 `.ruff_baseline`（逐文件 `文件=条数`），任何文件告警数不得高于基线；下降视为改善。
  当前基线只剩 **5 条有意保留的 catch-all**（`Goldenhandmaidens.py=3`、`pata.py=2`），原因写在基线注释里。
- 改动 `.md` 后跑 `markdownlint README.md CHANGELOG.md CLAUDE.md doc\*.md`（规则配置见 `.markdownlint.json`，
  中文长行 MD013 已关闭），要求零 error。
- 测试基线以 `python -m pytest -q` 实际结果为准（2026-11-14 实机校正批为 **422** 条；
  新增用例后同步更新本行）。
- **子进程一律走 `proc_util.run_hidden` / `popen_hidden`**：成品是 GUI 子系统（无控制台），
  裸调 `subprocess` 启动控制台子程序会给它新建一个黑框。`tests/test_20261114_hidden_console.py`
  用 AST 扫描全仓拦新增裸调用（`proc_util.py` 自身除外），不要绕过。
- **打包只走 `pwsh -NoProfile -File build.ps1 build -Python <Python3.13 解释器>`**：
  成品**唯一**在 `dist/goldenhandmaidens.exe`，桌面快捷方式也指向它；脚本用
  `--distpath dist`，打包后校验「dist 有成品」并在根目录仍有同名 exe 时**告警**（不自动删：
  环境的删除守卫会拦截，导致整次 build 假失败）。直接调 PyInstaller 或把产物
  放根目录都会造成「已修复的代码在实机上不生效」。详见 `doc/LIVE-DEBUGGING.md` §10。
- **增量构建会静默复用旧包**：PyInstaller 的 `.toc` 缓存按 mtime 判新旧，源码改动时间早于
  `.toc` 时直接跳过重建（表现：build 只跑 5 秒就 Complete，成品时间戳还是上一次的）。
  所以打包前先删 `dist/goldenhandmaidens.exe` 强制重建，完成后再核一次时间戳。
- 新增用例必须做负验证：故意改坏被测逻辑，用例必须失败。

## 动实机之前先读这几份

- `doc/LIVE-DEBUGGING.md`：实机调试方法学（前台锁与标题栏激活、点击「点→校验→补点」、
  模板标定、滚动为何要管理员、失败现场怎么取）。**改任何点击/判据代码前必读**。
- `doc/CLIENT-RESOLUTION.md`：客户区 1600×900 假设与偏移常量登记表——新增写死坐标要同步登记。
- `doc/GUI.md`：一屏三段式布局、缩放行为三条规则、配色与按钮三档语义、`_FlowRow`/`_ToggleBox`
  的自绘理由、定时提示链路、黑框真因与 `proc_util` 用法、GUI 框架评估与迁移触发条件。
  **改界面布局/控件/主题/子进程启动前必读**。
- 三条最容易踩的红线：`_drag_scroll` 与对提权窗口的注入都需要**管理员**权限；跳转型点击一律走
  `common.click_and_confirm`（点一次就返回 True 会掩盖「没进去」）；「标题匹配不到」不等于
  「点击被吞」（结算弹窗会压暗面板）。
