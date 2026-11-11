# 客户区 1600×900 假设与固定点位登记表

本项目的 OpenCV 模板与全部「固定点位 / 偏移」常量都基于**游戏客户区 1600×900**采集。
游戏 UI 不随窗口等比缩放：换窗口尺寸时，模板、点位、偏移会**同时**失效。
历史事故：首批愿望单模板在 1302×1080 下采集，换到 1600×900 后表现为
「已点击入口 → 未进入界面」，14 张模板与全部偏移重做。

## 单一尺寸来源

| 常量 | 值 | 定义位置 |
| --- | --- | --- |
| `common.CLIENT_WIDTH` | `1600` | `common.py` |
| `common.CLIENT_HEIGHT` | `900` | `common.py` |
| `common.BOTTOM_BAR_CLIENT_REGION` | `(0, CLIENT_HEIGHT - 250, CLIENT_WIDTH, 250)` | `common.py` |

`Goldenhandmaidens.run_scripts_thread` 启动任务时读取 `game_client_region()`，
尺寸不符时用 `CLIENT_WIDTH/HEIGHT` 打警告。新增代码引用分辨率时**必须引用这两个常量**，
不要再写字面量 `1600` / `900`。

## 固定点位 / 偏移登记表

坐标口径：`*_CLIENT_POS` 与 `*_REGION` 为**客户区相对坐标**；
`*_OFFSET` 为相对某个锚点模板中心的偏移（可为负）。全部来自 1600×900 实机实测。

| 模块 | 常量 | 值 / 含义 |
| --- | --- | --- |
| `common.py` | `BOTTOM_BAR_CLIENT_REGION` | 底部 250px 导航带 |
| `common.py` | `PROMO_OUTSIDE_POS` | `(150, 450)`：巅峰联赛介绍页卡片外空白 |
| `yuanwangdan.py` | `GIFT_CLICK_OFFSET` | `(68, 25)`：愿望单标题中心 → 进度礼盒 |
| `yuanwangdan.py` | `QTY_BUTTON_OFFSET` | `(110, -10)`：「开始」按钮中心 → 数量档 |
| `yuanwangdan.py` | `PATH_PROMPT_OFFSET_Y` | 屏幕中心 → 建筑交互提示（F） |
| `yuanwangdan.py` | `_close_by_blank_hint()` | 结算 / 领奖弹窗直接点「点击空白处关闭」模板中心，**不再用固定偏移**（旧版标题+偏移因流光动画与分辨率变化失准） |
| `hongbaolingqu.py` | `GUILD_WAR_*_POS` / `LAUREL_MENU_POS` / `TASK_*_POS` | 公会征伐、月桂之旅、任务面板 HUD 点位 |
| `hongbaolingqu.py` | `MILESTONE_TRACK_REGION` / `JOURNAL_*_POS` | 里程碑轨道、手记页签区域 |
| `dianfengjingjichang.py` | `SETTLEMENT_DISMISS_POS` / `OPPONENT_CLIENT_POS` | 失败页空白点、最弱对手卡片 |
| `fanfanle.py` | `KEYS_REGION` | 钥匙余量数字区域（静止/变化判据） |
| `haoyoujiangli.py` | `FRIENDS_HUD_POS` | 主界面右下角好友图标兜底入口 |
| `mimengzhiyu.py` | `MIMENG_TOP_RIGHT_REGION` | 右上角奖励入口区域 |
| `yingxiongtingtang.py` | `HERO_*_REGION` / `LEVEL_REGION` | 宝箱、领取、等级数字区域 |
| `lieshouxunshang.py` | `GRID_REGION` | 相对面板标题中心的悬赏卡片网格 |
| `tests/test_templates.py` | `CLIENT_WIDTH/HEIGHT` | 模板尺寸上限校验（与 `common` 对齐） |

## 换分辨率时必须一起做的事

1. 按新客户区**重采全部** `templates/*.png`（含 `templates/migong/`），
   按 [TEMPLATE-AUTHORING.md](TEMPLATE-AUTHORING.md) 做正/负样本与实点验证；
2. 逐个复测上表所有点位与偏移，更新常量值及其注释里的实测坐标；
3. 更新 `common.CLIENT_WIDTH/HEIGHT` 与本登记表；
4. 跑 `tests/test_client_constants.py` 与 `tests/test_templates.py`，再用一次实机跑验证
   「进入面板 → 点击 → 落地」三段链路。

## 机械校验

`tests/test_client_constants.py` 断言：尺寸常量值、底部导航带不越客户区、
登记表中的模块常量确实存在。`tests/test_templates.py` 断言全部模板尺寸不超过客户区。
两者只保证「登记与代码不脱节」，**不能替代实机标定**——点位是否点得中仍需实跑确认。
