"""阵容编辑模块：根据 formations.json 配置上阵英雄。

从游戏内读取当前阵容并保存到 formations.json，或将指定阵容应用到游戏中；
供推图/爬塔等任务在战斗前快速切换英雄配置。坐标类变量命名均带方位/序号后缀
（如 slot、confirm_btn）以明确用途。
"""

import json
import time
import os

from common import find_center, send_coord, get_work_path, get_template_path, get_resource_path
from drag_utils import send_drag


def deploy_formation(formation_name: str,
                     hero_templates: dict,
                     grid_offsets_path: str = "grid_offsets.json",
                     formation_config_path: str = "formations.json",
                     anchor_template: str = "zhandou.png",
                     anchor_subdir: str = "migong",
                     deselect_offset_y: int = -50,
                     drag_repeat: int = 2):
    # ① 加载阵容配置
    cfg_path = get_resource_path(formation_config_path)
    if not os.path.exists(cfg_path):
        print(f"阵容配置文件不存在: {cfg_path}")
        return False

    with open(cfg_path, "r", encoding="utf-8") as f:
        formations = json.load(f)

    if formation_name not in formations:
        print(f"阵容名不存在: {formation_name}")
        return False

    config = formations[formation_name]
    map_id = config["map"]
    steps = config["steps"]

    # ② 获取锚点
    anchor_path = get_template_path(anchor_template, subdir=anchor_subdir)
    anchor = find_center(anchor_path)
    if anchor is None:
        print(f"找不到锚点模板: {anchor_template}")
        return False
    anchor_x, anchor_y = anchor

    # ③ 加载格子映射
    offsets_path = get_resource_path(grid_offsets_path)
    if not os.path.exists(offsets_path):
        print(f"格子偏移文件不存在: {offsets_path}")
        return False

    with open(offsets_path, "r", encoding="utf-8") as f:
        grid_data = json.load(f)

    if map_id not in grid_data:
        print(f"地图编号不存在: {map_id}")
        return False

    offsets = grid_data[map_id]
    positions = {}
    for grid_id, (dx, dy) in offsets.items():
        positions[grid_id] = (anchor_x + dx, anchor_y + dy)

    # ④ 逐个处理角色
    for step in steps:
        hero = step["hero"]
        drags = step["drags"]

        # a. 获取该英雄的模板列表
        if hero not in hero_templates:
            print(f"英雄名不存在于 hero_templates 中: {hero}")
            continue

        templates = hero_templates[hero]
        if not templates:
            print(f"英雄 {hero} 没有模板文件，跳过")
            continue

        # b. 点击角色头像（只点一次）
        clicked = False
        for tpl_path in templates:
            pos = find_center(tpl_path)
            if pos is not None:
                send_coord(pos[0], pos[1])
                clicked = True
                break

        if not clicked:
            print(f"英雄 {hero} 所有模板均未匹配到，跳过")
            continue

        # c. 角色自动布置到前排（游戏机制，无需操作）
        # d. 短暂等待确保角色落位
        time.sleep(0.5)

        # e. 遍历 drags 列表，每条拖拽重复 drag_repeat 次
        for drag in drags:
            from_grid = str(drag["from"])
            to_grid = str(drag["to"])

            if from_grid not in positions:
                print(f"格子编号 {from_grid} 在地图 {map_id} 中不存在，跳过 {hero} 本次拖拽")
                continue
            if to_grid not in positions:
                print(f"格子编号 {to_grid} 在地图 {map_id} 中不存在，跳过 {hero} 本次拖拽")
                continue

            start_x, start_y = positions[from_grid]
            end_x, end_y = positions[to_grid]

            for i in range(drag_repeat):
                print(f"{hero} 拖拽 格子{from_grid}({start_x},{start_y}) → 格子{to_grid}({end_x},{end_y}) (第{i+1}/{drag_repeat}次)")
                send_drag(start_x, start_y, end_x, end_y)
                time.sleep(2.0)

    # ⑤ 完成
    return True
