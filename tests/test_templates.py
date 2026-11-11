"""模板资源一致性检查。

上一轮真实事故：`yuanwangdan.py` 连代码带它依赖的全部模板都没有 `git add`，
clone 仓库的人跑到该任务直接 `ValueError: 模板读取失败`，而当时的测试全绿。
本测试用机械扫描把这类问题挡在提交前：

1. 代码里字面量引用的每个模板都必须存在于 `templates/`（缺失即失败）；
2. **所有**模板（含 `templates/migong/` 子目录）尺寸不得超过 1600×900 客户区；
3. `flow_migong.py` 里动态拼名的 `click_mg` / `find_mg` 引用，必须在 migong 子目录有对应文件；
4. 未被字面量引用的模板数量不得超过基线（英雄/烙印模板按 ID 动态拼名属正常，
   但新增孤儿会被挡住）。

负验证留痕：
- 把 `_all_template_paths()` 改回只扫顶层，`test_migong_subdir_is_scanned` 必须失败；
- 删掉一张 migong 模板，`test_migong_literal_refs_exist` 必须失败；
- 新增一张未被引用的模板，`test_unreferenced_templates_within_baseline` 必须失败；
- 把尺寸校验的上限删掉，`test_templates_fit_client_area` 必须失败。
"""
import glob
import os
import re

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(ROOT, "templates")
CLIENT_WIDTH, CLIENT_HEIGHT = 1600, 900

# 只扫项目自身的任务/流程模块；开发期临时脚本不算数
SKIP_PREFIXES = ("_", "test_")

# 可选模板：代码在引用前会用 os.path.exists 判断，缺失时走降级分支而不是报错。
# 例：yijiannianya.png（女神塔「一键碾压」按钮）、kaishilianjin.png（炼金工坊「开始炼金」）
OPTIONAL_TEMPLATES = {"yijiannianya.png", "kaishilianjin.png", "nvshentasaodangwancheng.png"}

# 2026-11-07 基线：递归扫描得 471 个文件 / 466 个唯一 basename，其中 328 个未被
# `get_template_path("x.png")` 字面量引用（英雄模板、migong 烙印按 ID/名字动态拼名）。
# 设上限只拦「新增孤儿」，不要求清零——动态拼名的资源无法静态追踪。
UNREFERENCED_BASELINE = 328


def _scanned_modules():
    return [
        path for path in glob.glob(os.path.join(ROOT, "*.py"))
        if not os.path.basename(path).startswith(SKIP_PREFIXES)
    ]


def _all_template_paths():
    """递归收集全部模板文件，避免 `templates/migong/` 子目录成为校验盲区。"""
    return glob.glob(os.path.join(TEMPLATES_DIR, "**", "*.png"), recursive=True)


def _literal_template_refs():
    """收集 get_template_path("x.png") / get_template_path('x.png') 的字面量引用。"""
    refs = {}
    pattern = re.compile(r"""get_template_path\(\s*["']([^"']+\.png)["']""")
    for path in _scanned_modules():
        with open(path, encoding="utf-8") as handle:
            for name in pattern.findall(handle.read()):
                refs.setdefault(name, set()).add(os.path.basename(path))
    return refs


def test_referenced_templates_exist():
    refs = _literal_template_refs()
    assert refs, "未扫描到任何模板引用，说明扫描规则失效，需先修测试本身"

    missing = {
        name: sorted(users)
        for name, users in refs.items()
        if name not in OPTIONAL_TEMPLATES
        and not os.path.exists(os.path.join(TEMPLATES_DIR, name))
    }
    assert not missing, f"以下模板被代码引用但文件不存在：{missing}"


def test_templates_fit_client_area():
    """模板尺寸不能超过 1600×900 客户区；子目录同样受检。"""
    oversized = []
    for path in _all_template_paths():
        image = cv2.imread(path)
        if image is None:
            continue
        height, width = image.shape[:2]
        if width > CLIENT_WIDTH or height > CLIENT_HEIGHT:
            oversized.append((os.path.relpath(path, ROOT), width, height))
    assert not oversized, f"模板尺寸超出 1600×900 客户区：{oversized}"


def test_migong_subdir_is_scanned():
    """防回归：子目录模板必须真的进入扫描集合，否则上面两条断言都是半盲的。"""
    subdir_paths = [p for p in _all_template_paths()
                    if os.path.basename(os.path.dirname(p)) == "migong"]
    assert len(subdir_paths) > 100, "migong 子目录模板未被递归扫描"


def test_migong_literal_refs_exist():
    """`flow_migong` 用 `tpl(name)` 动态拼名，静态引用扫描看不到，这里单独校验。"""
    with open(os.path.join(ROOT, "flow_migong.py"), encoding="utf-8") as handle:
        source = handle.read()
    names = set(re.findall(r"""(?:click_mg|find_mg)\(\s*["']([a-zA-Z0-9_]+)["']""", source))
    assert names, "未解析到任何迷宫模板引用，说明正则失效"
    missing = sorted(name for name in names
                     if not os.path.exists(os.path.join(TEMPLATES_DIR, "migong", name + ".png")))
    assert not missing, f"迷宫模板引用缺失对应文件：{missing}"


def test_unreferenced_templates_within_baseline():
    """孤儿模板只按数量设上限，不再只打印不判断。"""
    refs = set(_literal_template_refs())
    existing = {os.path.basename(p) for p in _all_template_paths()}
    orphans = sorted(existing - refs)
    assert len(orphans) <= UNREFERENCED_BASELINE, (
        f"新增 {len(orphans) - UNREFERENCED_BASELINE} 个未被引用模板：{orphans[:8]}"
    )
