"""幻灵推图流程模块（薄封装）。

实际战斗逻辑在 push.py 中以 mode="huanling" 运行，本模块仅做转发与调试开关。
"""

from push import debug_lineup_recognition
from push import flow_push_mode1 as _push_flow

DEBUG_MODE = False


def flow_push_mode1(skip_manual=True, retry_count=3):
    return _push_flow(mode="huanling", skip_manual=skip_manual, retry_count=retry_count)


def main(skip_manual=True, retry_count=3):
    if DEBUG_MODE:
        debug_lineup_recognition()
    else:
        flow_push_mode1(skip_manual=skip_manual, retry_count=retry_count)
