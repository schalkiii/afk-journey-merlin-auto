"""日志格式化的回归测试：压缩高频行、任务归组缩进、边界行形状。

格式化只在出口做一次（GUI 的 log() 与 stdout tee 都走 format_body），
所以这里必须锁住「哪些行会被改写、哪些必须原样通过」——改写过头会把子脚本
自己判断用的措辞也吞掉。
"""
import log_format as lf


def setup_function(_func):
    lf.set_task(None)


def test_hit_line_is_compressed():
    assert lf.format_body(
        "caidan 识别成功，第 1 次，坐标: (3541, 958)，发送给 AHK 点击") == "命中 caidan (3541, 958) 第1次"


def test_retry_line_is_compressed():
    assert lf.format_body(
        "wanfamulu 第 3 次未找到，0.5 秒后重试（已等待 1.3 秒）...") == "未命中 wanfamulu 第3次（已等 1.3s）"


def test_giveup_line_is_compressed():
    assert lf.format_body("renwu 在 5.0 秒内未出现，放弃等待。") == "放弃 renwu（5.0s 内未出现）"


def test_state_transition_line_is_compressed():
    assert lf.format_body("start_battle -> monitor_battle") == "状态 start_battle → monitor_battle"


def test_other_wording_passes_through_unchanged():
    """没命中改写规则的行必须原样保留，不能因为「看起来像」就动它。"""
    plain = "【家园愿望单】当前不在家园视图，点击返回箭头后重试"
    assert lf.format_body(plain) == plain


def test_detail_lines_indent_under_the_running_task():
    lf.set_task("好友奖励")
    assert lf.format_body("菜单 识别成功，第 1 次，坐标: (3541, 958)，发送给 AHK 点击") == \
        "  · 命中 菜单 (3541, 958) 第1次"


def test_clearing_task_returns_lines_to_flush_left():
    lf.set_task("好友奖励")
    lf.set_task(None)
    assert lf.format_body("开始运行脚本") == "开始运行脚本"


def test_blank_input_produces_empty_body():
    assert lf.format_body("   \n") == ""


def test_module_tag_stays_at_line_start_after_compressing():
    """【模块名】不能被吞进短语中间——「放弃 【普竞】renwu（…）」这种行读不通。"""
    assert lf.format_body("【普竞】renwu 在 5.0 秒内未出现，放弃等待。") == \
        "【普竞】 放弃 renwu（5.0s 内未出现）"


def test_boundary_lines_stay_flush_left_inside_a_task():
    """开始/结束行是在 set_task 之后打的，不能被自己的缩进规则吃进去。"""
    lf.set_task("邮件")
    assert lf.format_body(lf.task_start_line(1, 3, "邮件")) == "▶ [1/3] 邮件"
    assert lf.format_body(lf.task_end_line(True, 1, 3, "邮件", 15.2)) == "✔ [1/3] 邮件 · 15.2s"


def test_boundary_lines_carry_index_result_and_duration():
    assert lf.task_start_line(3, 16, "好友奖励") == "▶ [3/16] 好友奖励"
    assert lf.task_end_line(True, 3, 16, "好友奖励", 20.05) == "✔ [3/16] 好友奖励 · 20.1s"
    assert lf.task_end_line(False, 4, 16, "普竞", 3.0) == "✘ [4/16] 普竞 · 3.0s"
