"""幻灵推图 - 薄封装，实际逻辑在 push.py 中以 mode="huanling" 运行。"""
from push import flow_push_mode1 as _push_flow, debug_lineup_recognition

DEBUG_MODE = False


def flow_push_mode1(skip_manual=True, retry_count=3):
    return _push_flow(mode="huanling", skip_manual=skip_manual, retry_count=retry_count)


def main(skip_manual=True, retry_count=3):
    if DEBUG_MODE:
        debug_lineup_recognition()
    else:
        flow_push_mode1(skip_manual=skip_manual, retry_count=retry_count)
