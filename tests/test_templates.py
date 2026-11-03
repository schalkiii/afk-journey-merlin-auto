"""模板资源一致性检查。

上一轮真实事故：`yuanwangdan.py` 连代码带它依赖的全部模板都没有 `git add`，
clone 仓库的人跑到该任务直接 `ValueError: 模板读取失败`，而当时的测试全绿。
本测试用机械扫描把这类问题挡在提交前：

1. 代码里字面量引用的每个模板都必须存在于 `templates/`（缺失即失败）；
2. 顶层模板尺寸不得超过 1600×900 客户区（按住分辨率错配：模板比画面还大必然匹配不到）；
3. 未被任何代码引用的模板只作为信息列出，不断言失败——英雄模板由仓库模块按 ID 动态拼名，
   静态扫描看不到引用属正常。
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
# 由用户按实际界面补图；未补时对应分支只覆盖已有建筑，不会报错。
OPTIONAL_TEMPLATES = {"yijiannianya.png", "kaishilianjin.png"}


def _scanned_modules():
    return [
        path for path in glob.glob(os.path.join(ROOT, "*.py"))
        if not os.path.basename(path).startswith(SKIP_PREFIXES)
    ]


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
    """模板尺寸不能超过 1600×900 客户区——超了说明是在别的分辨率/整屏下裁的。"""
    oversized = []
    for path in glob.glob(os.path.join(TEMPLATES_DIR, "*.png")):
        image = cv2.imread(path)
        if image is None:
            continue
        height, width = image.shape[:2]
        if width > CLIENT_WIDTH or height > CLIENT_HEIGHT:
            oversized.append((os.path.basename(path), width, height))
    assert not oversized, f"模板尺寸超出 1600×900 客户区：{oversized}"


def test_reports_unreferenced_templates(capsys):
    """未被字面量引用的模板只提示、不失败（英雄模板按 ID 动态拼名）。"""
    refs = set(_literal_template_refs())
    existing = {os.path.basename(p) for p in glob.glob(os.path.join(TEMPLATES_DIR, "*.png"))}
    orphans = sorted(existing - refs)
    print(f"\n未被代码字面量引用的模板 {len(orphans)} 个（英雄模板属正常）")
    if orphans:
        print("举例：", ", ".join(orphans[:8]))
    capsys.readouterr()
