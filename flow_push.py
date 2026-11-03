"""幻灵推图流程模块（薄封装）。

实际战斗逻辑在 push.py 中以 mode="huanling" 运行，本模块仅做转发与调试开关。
"""

import push as push_module
from push import debug_lineup_recognition
from push import flow_push_mode1 as _push_flow

DEBUG_MODE = False

# 最近一次运行的结束原因，语义与 push.LAST_STOP_REASON 一致：
# "fail_limit" 表示连续失败达到上限，循环推图应整体停止。
LAST_STOP_REASON = ""


def flow_push_mode1(skip_manual=True, retry_count=3, max_consecutive_failures=10):
    global LAST_STOP_REASON
    # 若 push 侧提前抛异常，保持空值，避免调用方读到上一次的 fail_limit
    LAST_STOP_REASON = ""
    result = _push_flow(
        mode="huanling",
        skip_manual=skip_manual,
        retry_count=retry_count,
        max_consecutive_failures=max_consecutive_failures,
    )
    LAST_STOP_REASON = push_module.LAST_STOP_REASON
    return result


def main(skip_manual=True, retry_count=3, max_consecutive_failures=10):
    global LAST_STOP_REASON
    if DEBUG_MODE:
        debug_lineup_recognition()
        LAST_STOP_REASON = ""
        return True
    else:
        return flow_push_mode1(
            skip_manual=skip_manual,
            retry_count=retry_count,
            max_consecutive_failures=max_consecutive_failures,
        )
