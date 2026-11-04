"""common 模板层性能优化测试：内存缓存、快速指纹与 APPDATA 模板同步。

全部在 tmp_path 内构造假模板目录与假 %APPDATA%，不读写真实 APPDATA、
不启动游戏。模板缓存用打桩的 cv2.imread，避免依赖真实 PNG 解码开销。
"""
import os
import sys as real_sys

import numpy as np
import pytest

import common

BUNDLED_FILES = {
    "a.png": b"alpha-data",
    "sub/b.png": b"beta-data",
}


@pytest.fixture(autouse=True)
def reset_template_cache():
    """模板缓存是模块级状态，测试之间必须清空，避免上一个用例的命中影响下一个。"""
    common._template_cache.clear()
    yield
    common._template_cache.clear()


@pytest.fixture
def frozen_app(tmp_path, monkeypatch):
    """构造 frozen 运行环境：内置模板目录 + 独立的 APPDATA 目录。"""
    bundle_root = tmp_path / "bundle"
    bundled_dir = bundle_root / "templates"
    for rel, data in BUNDLED_FILES.items():
        path = bundled_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    app_root = tmp_path / "appdata"
    app_templates = app_root / "templates"

    monkeypatch.setattr(common, "APP_DATA_ROOT", str(app_root))
    monkeypatch.setattr(common, "APP_TEMPLATES_DIR", str(app_templates))
    monkeypatch.setattr(common, "get_resource_path", lambda rel: str(bundle_root / rel))
    monkeypatch.setattr(real_sys, "frozen", True, raising=False)
    monkeypatch.setattr(common, "_ACTIVE_TEMPLATES_DIR", None)

    yield bundled_dir, app_root, app_templates


def _read_marker_lines(app_root):
    marker_path = os.path.join(str(app_root), "templates.marker")
    with open(marker_path, encoding="utf-8") as stream:
        return [line for line in stream.read().splitlines() if line.strip()]


def test_load_template_reuses_cached_array(monkeypatch, tmp_path):
    """同一路径连续两次必须返回同一对象，且只解码一次。"""
    template_path = tmp_path / "t.png"
    template_path.write_bytes(b"placeholder")
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    calls = []

    def fake_imread(path, flags):
        calls.append(path)
        return image

    monkeypatch.setattr(common.cv2, "imread", fake_imread)

    first = common.load_template(str(template_path))
    second = common.load_template(str(template_path))
    assert first is second
    assert len(calls) == 1


def test_cache_invalidated_after_file_change(monkeypatch, tmp_path):
    """mtime 变化后 key 失效，必须重新解码并返回新对象。"""
    template_path = tmp_path / "t.png"
    template_path.write_bytes(b"v1")
    stat = template_path.stat()
    images = iter([
        np.full((2, 2, 3), 1, dtype=np.uint8),
        np.full((2, 2, 3), 2, dtype=np.uint8),
    ])
    calls = []

    def fake_imread(path, flags):
        calls.append(path)
        return next(images)

    monkeypatch.setattr(common.cv2, "imread", fake_imread)

    first = common.load_template(str(template_path))
    os.utime(template_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    second = common.load_template(str(template_path))

    assert len(calls) == 2
    assert first is not second
    assert int(second[0, 0, 0]) == 2


def test_cache_size_change_invalidates(monkeypatch, tmp_path):
    """文件大小变化同样属于 key 变化，不能继续命中旧缓存。"""
    template_path = tmp_path / "t.png"
    template_path.write_bytes(b"short")
    calls = []

    def fake_imread(path, flags):
        calls.append(path)
        return np.zeros((2, 2, 3), dtype=np.uint8)

    monkeypatch.setattr(common.cv2, "imread", fake_imread)

    common.load_template(str(template_path))
    template_path.write_bytes(b"much-longer")
    common.load_template(str(template_path))

    assert len(calls) == 2


def test_cache_evicts_oldest_entry(monkeypatch, tmp_path):
    """超过上限时淘汰最久未使用的条目（LRU）。"""
    monkeypatch.setattr(common, "_TEMPLATE_CACHE_MAX", 3)
    paths = []
    calls = []

    def fake_imread(path, flags):
        calls.append(path)
        return np.zeros((2, 2, 3), dtype=np.uint8) + len(calls)

    monkeypatch.setattr(common.cv2, "imread", fake_imread)

    for index in range(4):
        path = tmp_path / f"t{index}.png"
        path.write_bytes(b"data")
        paths.append(path)
        common.load_template(str(path))

    assert len(common._template_cache) == 3
    first_key = common._template_cache_key(str(paths[0]))
    assert first_key not in common._template_cache

    common.load_template(str(paths[0]))
    assert len(calls) == 5


def test_failed_read_is_not_cached_and_raises(monkeypatch, tmp_path):
    """cv2.imread 返回 None 时必须抛 ValueError，且失败结果不得进入缓存。"""
    template_path = tmp_path / "broken.png"
    template_path.write_bytes(b"not-a-real-png")
    monkeypatch.setattr(real_sys, "frozen", False, raising=False)
    calls = []

    def fake_imread(path, flags):
        calls.append(path)

    monkeypatch.setattr(common.cv2, "imread", fake_imread)

    with pytest.raises(ValueError):
        common.load_template(str(template_path))
    with pytest.raises(ValueError):
        common.load_template(str(template_path))

    assert len(calls) == 2
    assert len(common._template_cache) == 0


def test_missing_file_skips_cache(monkeypatch, tmp_path):
    """os.stat 失败时跳过缓存，保持原有 ValueError 语义。"""
    template_path = tmp_path / "missing.png"
    monkeypatch.setattr(real_sys, "frozen", False, raising=False)
    monkeypatch.setattr(common.cv2, "imread", lambda path, flags: None)

    with pytest.raises(ValueError):
        common.load_template(str(template_path))
    assert len(common._template_cache) == 0


class _DeepCheckNotAllowed(BaseException):
    """BaseException 子类：ensure 的 except Exception 不会把它吞掉。"""


def test_first_ensure_copies_and_writes_marker(frozen_app):
    _, app_root, app_templates = frozen_app

    common.ensure_appdata_templates()

    assert common._ACTIVE_TEMPLATES_DIR == str(app_templates)
    for rel, data in BUNDLED_FILES.items():
        assert (app_templates / rel).read_bytes() == data
    assert len(_read_marker_lines(app_root)) == 2


def test_second_ensure_uses_fast_marker_without_deep_check(frozen_app, monkeypatch):
    """marker 一致时必须走快速路径，不得触发全量 sha256。"""
    _, app_root, app_templates = frozen_app
    common.ensure_appdata_templates()

    def forbidden(_templates_dir):
        raise _DeepCheckNotAllowed("快速指纹命中时不得调用 _templates_marker")

    monkeypatch.setattr(common, "_templates_marker", forbidden)

    common.ensure_appdata_templates()
    assert common._ACTIVE_TEMPLATES_DIR == str(app_templates)
    assert len(_read_marker_lines(app_root)) == 2


def test_missing_appdata_file_triggers_recopy(frozen_app):
    _, _, app_templates = frozen_app
    common.ensure_appdata_templates()

    (app_templates / "sub" / "b.png").unlink()
    common.ensure_appdata_templates()

    assert (app_templates / "sub" / "b.png").read_bytes() == BUNDLED_FILES["sub/b.png"]
    assert common._ACTIVE_TEMPLATES_DIR == str(app_templates)


def test_bundled_same_size_content_change_triggers_recopy(frozen_app):
    """内置模板大小不变但采样区内容变化，也必须被发现并重拷贝。"""
    bundled_dir, _, app_templates = frozen_app
    common.ensure_appdata_templates()

    (bundled_dir / "a.png").write_bytes(b"alpha-datX")
    common.ensure_appdata_templates()

    assert (app_templates / "a.png").read_bytes() == b"alpha-datX"


@pytest.mark.parametrize("marker_content", [None, "garbage\nonly-one-line\n"])
def test_missing_or_corrupt_marker_falls_back_to_deep_check(frozen_app, marker_content):
    """marker 缺失/损坏不能崩溃：走深度校验后重建 marker。"""
    _, app_root, app_templates = frozen_app
    common.ensure_appdata_templates()

    marker_path = app_root / "templates.marker"
    if marker_content is None:
        marker_path.unlink()
    else:
        marker_path.write_text(marker_content, encoding="utf-8")

    common.ensure_appdata_templates()

    assert common._ACTIVE_TEMPLATES_DIR == str(app_templates)
    assert len(_read_marker_lines(app_root)) == 2


def test_dev_mode_never_touches_appdata(frozen_app, monkeypatch, tmp_path):
    bundled_dir, app_root, _ = frozen_app
    monkeypatch.setattr(real_sys, "frozen", False, raising=False)

    common.ensure_appdata_templates()

    assert common._ACTIVE_TEMPLATES_DIR == str(bundled_dir)
    assert not app_root.exists()
