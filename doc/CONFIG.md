# 用户配置说明

本项目的**唯一**用户配置文件是运行时生成的 `game_bot_config.json`（位于程序工作目录，
由 `bot_runtime.CONFIG_FILE` 指定）。历史上仓库里还有一个 `config.json`，但它从未被任何
代码读取，2026-11-07 已删除并加入 `.gitignore`；不要照着旧文档新建它。

## 顶层字段

读写位置：`bot_runtime.load_config()` / `save_config()`（整体 JSON 读写），
`Goldenhandmaidens.GameBotGUI` 负责各字段的默认值、控件绑定与保存。

| 字段 | 类型 | 默认 | 含义 / 读写位置 |
| --- | --- | --- | --- |
| `scripts` | object | `{}` | 按任务名存 `{enabled, params, last_run_time}`；GUI 初始化时逐项覆盖 `ScriptConfig`，用户在左侧列表勾选即写回 |
| `script_order` | array[string] | `[]` | 用户拖拽后的执行顺序（任务名列表）；重启时按此排序，未列入的新功能补到末尾。列表顺序即执行顺序，没有第二份硬编码顺序表 |
| `auto_configure_lineup` | bool | 见 GUI 控制栏 | 挑战前自动采用「通关阵容」 |
| `auto_start_on_launch` | bool | `false` | 程序启动后立即开始运行 |
| `launch_game_on_open` | bool | 见 GUI 控制栏 | 定时到点或点「启动游戏并运行」时先启动游戏 |
| `game_launch_delay` | int | `20` | 启动游戏后等待的秒数（之后还会等界面真正就绪，见 `wait_for_game_ready`） |
| `schedule_time` | string | `""` | 定时开始，格式 `HH:MM`；解析失败时忽略，不中断启动 |
| `remote_desktop_compat` | bool | 见 GUI 控制栏 | 后台截图 + 点击前自动激活游戏窗口 |
| `restore_cursor_after_click` | bool | 见 GUI 控制栏 | 每次注入点击后把光标放回原处 |
| `push_settings` | object | `{}` | 推图类任务的参数集合（连续失败上限、轮次等） |
| `first_run_completed` | bool | `false` | 首次运行标记 |

`scripts.<任务名>.params` 的常见键（由各任务配置面板写入）：
`challenges`、`floors`、`formation_name`、`shenceng_formation_name`、`challenge_count`、
`fail_limit`、`max_rounds`、`paid_times`、`quick_upgrade_times`、`retry_count`。
新增参数时同步在 `Goldenhandmaidens.py` 的 `ScriptConfig(...)` 默认值与配置面板控件里登记。

## 其它运行时文件（不是用户配置）

| 路径 | 用途 |
| --- | --- |
| `shared/target_coord.txt` | 点击 IPC：Python `send_coord` 写入整屏绝对坐标，提权 `click_from_file.exe` 读取后删除并注入点击 |
| `game_bot.log` | 运行日志（UTF-8，超过 5 MB 轮转为 `.1`） |
| `warehouse_heroes.txt` | 仓库扫描结果，供 `flow_tower` 判断阵容练度 |
| `debug/failures/<时间>_<任务名>/` | 任务失败/超时时留存的最近 5 帧截图 |

以上均由 `.gitignore` 忽略，不进版本库。

## 修改配置时的注意事项

1. 改字段要同步三处：默认值（`Goldenhandmaidens.py` 初始化）、控件绑定、`save_config()` 的写入点；
   只改其中一处会出现「界面显示与落盘不一致」。
2. `script_order` 只存任务名；重命名任务会让旧顺序项失效（按「新功能补到末尾」处理）。
3. 配置解析失败时 `load_config()` 返回 `{}`，程序按默认值启动，不会弹错——排查「设置没生效」
   时先确认文件本身是合法 JSON。
