"""日志格式化的回归测试：压缩高频行、任务归组缩进、边界行形状。

格式化只在出口做一次（GUI 的 log() 与 stdout tee 都走 format_body），
所以这里必须锁住「哪些行会被改写、哪些必须原样通过」——改写过头会把子脚本
自己判断用的措辞也吞掉。
"""
import io
import re
import time

import bot_runtime
import log_format as lf

TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "Goldenhandmaidens.py", line 1705, in run_scripts_thread\n'
    "ValueError: 示例异常"
)
LINE_WITH_TIMESTAMP = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] .+$")


def setup_function(_func):
    lf.set_task(None)


def test_hit_line_is_compressed():
    assert lf.format_body(
        "caidan 识别成功，第 1 次，坐标: (3541, 958)，发送给 AHK 点击") == \
        "命中 菜单(caidan) (3541, 958) 第1次"


def test_retry_line_is_compressed():
    assert lf.format_body(
        "wanfamulu 第 3 次未找到，0.5 秒后重试（已等待 1.3 秒）...") == \
        "未命中 玩法目录(wanfamulu) 第3次（已等 1.3s）"


def test_giveup_line_is_compressed():
    assert lf.format_body("renwu 在 5.0 秒内未出现，放弃等待。") == "放弃 任务(renwu)（5.0s 内未出现）"


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
        "【普竞】 放弃 任务(renwu)（5.0s 内未出现）"


def test_translated_names_and_paths_are_left_alone():
    """已转过的「中文(拼音)」与文件路径里的拼音名不能再被二次替换。"""
    assert lf.format_body("命中 玩法目录(wanfamulu) (1080, 940) 第1次") == \
        "命中 玩法目录(wanfamulu) (1080, 940) 第1次"
    assert lf.format_body("模板不存在: templates/pujing.png") == "模板不存在: templates/pujing.png"


def test_boundary_lines_stay_flush_left_inside_a_task():
    """开始/结束行是在 set_task 之后打的，不能被自己的缩进规则吃进去。"""
    lf.set_task("邮件")
    assert lf.format_body(lf.task_start_line(1, 3, "邮件")) == "▶ [1/3] 邮件"
    assert lf.format_body(lf.task_end_line(True, 1, 3, "邮件", 15.2)) == "✔ [1/3] 邮件 · 15.2s"


def test_boundary_lines_carry_index_result_and_duration():
    assert lf.task_start_line(3, 16, "好友奖励") == "▶ [3/16] 好友奖励"
    assert lf.task_end_line(True, 3, 16, "好友奖励", 20.05) == "✔ [3/16] 好友奖励 · 20.1s"
    assert lf.task_end_line(False, 4, 16, "普竞", 3.0) == "✘ [4/16] 普竞 · 3.0s"


def test_format_multiline_drops_blank_rows():
    assert lf.format_multiline("甲\n\n乙\n") == ["甲", "乙"]


def _persist_bodies(monkeypatch, tmp_path, bodies):
    """按 GUI 异常路径的写法把正文逐行带戳落盘，返回文件里的行。"""
    log_path = tmp_path / "game_bot.log"
    monkeypatch.setattr(bot_runtime, "LOG_FILE", str(log_path))
    for body in bodies:
        bot_runtime.append_log_file(f"[{time.strftime('%H:%M:%S')}] {body}\n")
    return log_path.read_text(encoding="utf-8").splitlines()


def test_multiline_traceback_persists_one_stamped_line_per_row(monkeypatch, tmp_path):
    lines = _persist_bodies(monkeypatch, tmp_path, lf.format_multiline(TRACEBACK))

    assert len(lines) == 3, f"三行堆栈应落盘三行，实际 {lines}"
    for line in lines:
        assert LINE_WITH_TIMESTAMP.match(line), f"缺时间戳：{line!r}"
        # 不在任务里时顶格，不能被 detail 缩进
        assert not line.split("] ", 1)[1].startswith(lf.DETAIL_MARK), f"不应缩进：{line!r}"


def test_multiline_traceback_is_grouped_under_running_task(monkeypatch, tmp_path):
    lf.set_task("普竞")
    try:
        bodies = lf.format_multiline(TRACEBACK)
    finally:
        lf.set_task(None)
    lines = _persist_bodies(monkeypatch, tmp_path, bodies)

    assert len(lines) == 3, f"三行堆栈应落盘三行，实际 {lines}"
    for line in lines:
        assert line.split("] ", 1)[1].startswith(lf.DETAIL_MARK), f"任务中的堆栈行必须缩进：{line!r}"


def _write_persistent(monkeypatch, tmp_path, chunks):
    """构造早期 stdout 包装并喂入分片，返回（日志路径, 控制台流, 包装对象）。"""
    log_path = tmp_path / "game_bot.log"
    monkeypatch.setattr(bot_runtime, "LOG_FILE", str(log_path))
    stream = io.StringIO()
    stdout = bot_runtime._PersistentStdout(stream, str(log_path))
    for chunk in chunks:
        stdout.write(chunk)
    return log_path, stream, stdout


def test_persistent_stdout_buffers_half_line_until_newline(monkeypatch, tmp_path):
    log_path, stream, _ = _write_persistent(monkeypatch, tmp_path, ["abc", "def\n"])

    # 控制台即时拿到原始文本，文件侧只在凑齐一条完整行时才落盘
    assert stream.getvalue() == "abcdef\n"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, f"半行不应提前落盘，实际 {lines}"
    assert "abcdef" in lines[0]
    assert LINE_WITH_TIMESTAMP.match(lines[0])


def test_persistent_stdout_splits_one_multi_line_write(monkeypatch, tmp_path):
    log_path, _, _ = _write_persistent(monkeypatch, tmp_path, ["第一行\n第二行\n"])

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, f"一次写入的两行都应落盘，实际 {lines}"
    assert "第一行" in lines[0]
    assert "第二行" in lines[1]


def test_persistent_stdout_flush_persists_pending(monkeypatch, tmp_path):
    log_path, _, stdout = _write_persistent(monkeypatch, tmp_path, ["尾巴"])

    stdout.flush()
    stdout.flush()   # 再刷一次不能把同一条 pending 重复落盘

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, f"flush 应把 pending 按一行落盘且不重复，实际 {lines}"
    assert "尾巴" in lines[0]
