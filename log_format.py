"""日志行的统一格式。

只在**出口**整理一次（GUI 的 `log()` 与 stdout tee 两条路都走这里），不去改三十个流程
模块里的 print——那些行的措辞各不相同，逐个改既容易漏，又可能碰到判定逻辑。

整理做三件事：
1. 任务运行期间的子脚本行统一缩进并加 `·`，让「命中 caidan」这类行看得出属于哪个任务
   （以前只能往上翻找「开始执行」）；
2. 把占日志大头的两类高频行压短（实测一份日常日志里「识别成功」717 行、「未找到重试」1322 行）；
3. 任务边界用一行标出来，带序号、结果和耗时。
"""

import re

# 当前任务名。任务循环里同步设置（不能用 root.after，那是异步的，会漏掉紧随其后的行）。
# 单运行循环假设：工作线程写、GUI log 与 stdout tee 读；并行启动第二个运行循环会互相覆盖。
_task = None

# 高频行压缩：措辞固定、量大，压成等宽短语后一眼能扫。
# 只匹配「整行就是这个形状」的情况，避免误伤别的措辞。
_RULES = (
    (re.compile(r"^(?P<name>.+?) 识别成功，第 (?P<times>\d+) 次，坐标: (?P<pos>\(\d+, \d+\))"
                r"(?P<tail>，发送给 AHK 点击)?$"),
     lambda m: f"命中 {m['name']} {m['pos']} 第{m['times']}次"),
    (re.compile(r"^(?P<name>.+?) 第 (?P<times>\d+) 次未找到，0\.5 秒后重试"
                r"（已等待 (?P<waited>[\d.]+) 秒）\.\.\.?$"),
     lambda m: f"未命中 {m['name']} 第{m['times']}次（已等 {m['waited']}s）"),
    (re.compile(r"^(?P<name>.+?) 在 (?P<timeout>[\d.]+) 秒内未出现，放弃等待。?$"),
     lambda m: f"放弃 {m['name']}（{m['timeout']}s 内未出现）"),
    (re.compile(r"^(?P<src>[A-Za-z_][\w]*) -> (?P<dst>[A-Za-z_][\w]*)$"),
     lambda m: f"状态 {m['src']} → {m['dst']}"),
)

DETAIL_MARK = "  · "
# 边界标记顶格：任务开始/结束行是在 set_task 之后打出来的，不排掉就会被自己的
# 缩进规则吃进去，变成「· ▶ [1/3] 邮件」这种既不顶格也不像 detail 的行。
BOUNDARY_MARKS = ("▶", "✔", "✘")
# 子脚本常以「【模块名】」开头。压缩规则要把这段留在行首，否则会嵌进短语中间，
# 变成「放弃 【普竞】renwu（5.0s 内未出现）」这种读不通的行。
MODULE_PREFIX = re.compile(r"^(?P<tag>【[^】]+】)\s*(?P<rest>.*)$")


def set_task(name):
    """标记当前正在执行的任务；传 None / 空串表示不在任何任务里（GUI 自身的事件行）。"""
    global _task
    _task = name or None


def current_task():
    return _task


def _compress(body):
    """命中高频行规则就改写，否则原样返回。"""
    for pattern, render in _RULES:
        matched = pattern.match(body)
        if matched:
            return render(matched)
    return body


def format_body(text):
    """把一行日志正文整理成最终形式（不含 `[HH:MM:SS]` 前缀）。"""
    body = str(text).strip()
    if not body:
        return ""
    tagged = MODULE_PREFIX.match(body)
    if tagged:
        rest = _compress(tagged["rest"])
        # 没命中任何压缩规则就整行原样通过——顺手在【标签】后加个空格也是无谓的改动
        if rest != tagged["rest"]:
            body = f"{tagged['tag']} {rest}"
    else:
        body = _compress(body)
    if body.startswith(BOUNDARY_MARKS):
        return body
    return f"{DETAIL_MARK}{body}" if _task else body


def format_multiline(text):
    """把多行文本（异常堆栈这类）逐行整理成正文列表，空行丢弃。

    逐行而不是整段处理，是为了让每一行都能独立带 `[HH:MM:SS]` 前缀并排进任务上下文。
    """
    return [body for body in (format_body(line) for line in str(text).splitlines()) if body]


def task_start_line(index, total, name):
    """任务开始行。"""
    return f"▶ [{index}/{total}] {name}"


def task_end_line(ok, index, total, name, duration):
    """任务结束行：✔ 成功 / ✘ 失败，带耗时。"""
    mark = "✔" if ok else "✘"
    return f"{mark} [{index}/{total}] {name} · {duration:.1f}s"
