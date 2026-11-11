"""模板 / 动作中文名映射的完整性与分类校验。

负验证留痕：
- 新增一张 `get_template_path("new.png")` 引用但不在 `LOG_NAME_MAP` 登记，
  `test_all_literal_template_refs_have_cn_name` 必须失败；
- 往 `TEMPLATE_CN` 里塞一个没有同名 PNG 的键，`test_template_cn_keys_have_png` 必须失败；
- 把 `common` 的 re-export 删掉，`test_common_reexports_name_tables` 必须失败。
"""

import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common
import template_names

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(ROOT, "templates")


def _literal_ref_bases():
    refs = set()
    for path in glob.glob(os.path.join(ROOT, "*.py")):
        with open(path, encoding="utf-8") as handle:
            for name in re.findall(r"""get_template_path\(\s*["']([^"']+\.png)["']""", handle.read()):
                refs.add(os.path.splitext(name)[0])
    return refs


def test_all_literal_template_refs_have_cn_name():
    refs = _literal_ref_bases()
    assert refs, "未扫描到模板引用，扫描规则失效"
    missing = sorted(refs - set(template_names.LOG_NAME_MAP))
    assert not missing, f"以下模板引用缺少中文名标注：{missing}"


def test_template_cn_keys_have_png():
    missing = sorted(k for k in template_names.TEMPLATE_CN
                     if not os.path.exists(os.path.join(TEMPLATES_DIR, k + ".png")))
    assert not missing, f"TEMPLATE_CN 含无同名 PNG 的键：{missing}"


def test_action_cn_keys_are_not_template_files():
    """动作名与可选模板名单独成表，避免模板表持续混入非模板项。"""
    misplaced = sorted(k for k in template_names.ACTION_CN
                       if os.path.exists(os.path.join(TEMPLATES_DIR, k + ".png")))
    assert not misplaced, f"ACTION_CN 含已有 PNG 的键，应迁入 TEMPLATE_CN：{misplaced}"


def test_log_name_map_is_union():
    assert set(template_names.LOG_NAME_MAP) == (
        set(template_names.TEMPLATE_CN) | set(template_names.ACTION_CN)
    )


def test_common_reexports_name_tables():
    assert common.TEMPLATE_CN is template_names.TEMPLATE_CN
    assert common.LOG_NAME_MAP is template_names.LOG_NAME_MAP
    assert common.display_name("caidan") == "菜单(caidan)"


def test_display_name_keeps_retry_suffix():
    assert common.display_name("kuaisushengji(2)") == "快速升级(kuaisushengji)(2)"
