"""game_bot.log 的行完整性与时间戳回归测试。

调试时靠这份日志看时序，所以两个性质必须守住：
- 每一行都带 [HH:MM:SS] 前缀（子脚本 print 是分两次写入的，容易漏）；
- 一次 print 只产生一行日志，不被换行拆成两条。
"""
import re
import sys

import bot_runtime

LINE_WITH_TIMESTAMP = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] .+$")


def _capture_tee_lines(monkeypatch, tmp_path, emit):
    log_file = str(tmp_path / "game_bot.log")
    monkeypatch.setattr(bot_runtime, "LOG_FILE", log_file)
    collected = []
    tee = bot_runtime._StdoutTee(collected.append)
    original = sys.stdout
    sys.stdout = tee
    try:
        emit()
    finally:
        sys.stdout = original
    return open(log_file, encoding="utf-8").read().splitlines(), collected


def test_stdout_lines_are_persisted_with_timestamps(monkeypatch, tmp_path):
    def emit():
        print("caidan 识别成功，第 1 次，坐标: (3541, 958)")
        print("多行第一条")
        print("带", "多个参数")

    lines, panel_messages = _capture_tee_lines(monkeypatch, tmp_path, emit)

    assert len(lines) == 3, f"应落盘 3 行，实际 {lines}"
    for line in lines:
        assert LINE_WITH_TIMESTAMP.match(line), f"缺时间戳：{line!r}"
    assert "多个参数" in lines[-1]
    assert panel_messages, "面板汇聚不应为空"


def test_log_file_keeps_one_line_per_print(monkeypatch, tmp_path):
    def emit():
        print("第一行")
        print("第二行")

    lines, _ = _capture_tee_lines(monkeypatch, tmp_path, emit)
    assert [line.split("] ", 1)[1] for line in lines] == ["第一行", "第二行"]
