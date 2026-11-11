"""客户区尺寸常量与固定点位登记表的机械校验。

只保证「登记与代码不脱节」，不能替代实机标定。负验证留痕：
- 把 `common.CLIENT_WIDTH` 改成 1599，`test_client_size_constants` 必须失败；
- 把 `BOTTOM_BAR_CLIENT_REGION` 的底边改成超出客户区，`test_bottom_bar_region_within_client` 必须失败；
- 删除任一登记常量，`test_registered_position_constants_exist` 必须失败。
"""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common

REGISTERED_CONSTANTS = {
    "common": ["CLIENT_WIDTH", "CLIENT_HEIGHT", "BOTTOM_BAR_CLIENT_REGION", "PROMO_OUTSIDE_POS"],
    "yuanwangdan": ["GIFT_CLICK_OFFSET", "QTY_BUTTON_OFFSET", "PATH_PROMPT_OFFSET_Y"],
    "dianfengjingjichang": ["SETTLEMENT_DISMISS_POS", "OPPONENT_CLIENT_POS"],
    "fanfanle": ["KEYS_REGION"],
    "haoyoujiangli": ["FRIENDS_HUD_POS"],
    "hongbaolingqu": ["GUILD_WAR_TAB_POS", "LAUREL_MENU_POS", "MILESTONE_TRACK_REGION"],
    "mimengzhiyu": ["MIMENG_TOP_RIGHT_REGION"],
    "yingxiongtingtang": ["LEVEL_REGION"],
    "lieshouxunshang": ["GRID_REGION"],
}


def test_client_size_constants():
    assert (common.CLIENT_WIDTH, common.CLIENT_HEIGHT) == (1600, 900)


def test_bottom_bar_region_within_client():
    x, y, width, height = common.BOTTOM_BAR_CLIENT_REGION
    assert x >= 0 and y >= 0
    assert x + width <= common.CLIENT_WIDTH
    assert y + height <= common.CLIENT_HEIGHT


def test_registered_position_constants_exist():
    for module_name, names in REGISTERED_CONSTANTS.items():
        module = importlib.import_module(module_name)
        for name in names:
            assert hasattr(module, name), f"doc/CLIENT-RESOLUTION.md 登记的 {module_name}.{name} 不存在"


def test_all_fixed_points_within_client_area():
    """客户区相对点位不得越界（偏移常量允许负值，单独跳过）。"""
    points = [
        ("PROMO_OUTSIDE_POS", common.PROMO_OUTSIDE_POS),
        ("OPPONENT_CLIENT_POS", importlib.import_module("dianfengjingjichang").OPPONENT_CLIENT_POS),
        ("LAUREL_MENU_POS", importlib.import_module("hongbaolingqu").LAUREL_MENU_POS),
    ]
    for label, (x, y) in points:
        assert 0 <= x <= common.CLIENT_WIDTH and 0 <= y <= common.CLIENT_HEIGHT, label
