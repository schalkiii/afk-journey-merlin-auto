"""更新链路的安全约束与决策逻辑测试（不联网、不碰真实 exe）。

负验证留痕：
- 把 `updater.UPDATE_REPO` 改回 `yangyh02/...`，`test_update_source_is_this_fork` 必须失败；
- 删掉 `_select_exe_asset` 的体积/扩展名校验，`test_select_exe_asset_*` 必须失败；
- 删掉 `install_and_restart` 里的 `.bak` 回滚段，`test_install_writes_backup_and_rollback` 必须失败；
- 把 `check_update` 的异常分支改回 2 元组，`test_check_update_*` 的三条契约用例必须失败。
"""

import importlib
import sys

import pytest

updater = importlib.import_module("updater")


class _FakeResponse:
    """模拟 urlopen 的返回：既是上下文管理器，又提供 read() 与 headers。"""

    def __init__(self, payload, content_length=0):
        self._payload = payload
        self._read = False
        self.headers = {"Content-Length": str(content_length)}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        if self._read:
            return b""
        self._read = True
        return self._payload


def _release(tag, assets):
    import json

    return json.dumps({
        "tag_name": tag,
        "html_url": f"https://example.invalid/releases/{tag}",
        "assets": assets,
    }).encode("utf-8")


def test_update_source_is_this_fork():
    """更新源必须是本 fork；指向上游会把本仓库增强覆盖掉。"""
    assert "yangyh02" not in updater.GITHUB_API
    assert "yangyh02" not in updater.UPDATE_REPO
    assert "schalkiii/afk-journey-merlin-auto" in updater.GITHUB_API


def test_parse_version():
    assert updater._parse_version("v1.4.7") == (1, 4, 7)
    assert updater._parse_version("no digits") == ()


def test_select_exe_asset_accepts_only_named_sized_exe(monkeypatch):
    assets = [
        {"name": "source.zip", "size": 9_999_999, "browser_download_url": "https://x/zip"},
        {"name": "other.exe", "size": 9_999_999, "browser_download_url": "https://x/other"},
        {"name": "goldenhandmaidens.exe", "size": 1024, "browser_download_url": "https://x/tiny"},
        {"name": "goldenhandmaidens.exe", "size": 5_000_000, "browser_download_url": "https://x/good"},
    ]
    assert updater._select_exe_asset(assets) == ("https://x/good", 5_000_000)


def test_select_exe_asset_rejects_unusable_assets():
    assert updater._select_exe_asset([]) == ("", 0)
    assert updater._select_exe_asset([{"name": "goldenhandmaidens.exe", "size": 5_000_000}]) == ("", 0)
    assert updater._select_exe_asset([{"name": "notes.txt", "size": 5_000_000,
                                       "browser_download_url": "https://x/txt"}]) == ("", 0)


def test_check_update_error_returns_four_tuple(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("network down")

    monkeypatch.setattr(updater.urllib.request, "urlopen", boom)
    result = updater.check_update()
    assert len(result) == 4
    assert result[0] is None and result[3] == "network down"


def test_check_update_skips_release_without_installable_asset(monkeypatch):
    payload = _release("v9.9.9", [{"name": "source.zip", "size": 9_999_999,
                                   "browser_download_url": "https://x/zip"}])
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *_a, **_k: _FakeResponse(payload))
    has_update, tag, url, message = updater.check_update()
    assert has_update is False and tag == "v9.9.9" and url == ""
    assert "未提供可安装" in message


def test_check_update_accepts_valid_release(monkeypatch):
    payload = _release("v9.9.9", [{"name": "goldenhandmaidens.exe", "size": 5_000_000,
                                   "browser_download_url": "https://x/exe"}])
    monkeypatch.setattr(updater.urllib.request, "urlopen",
                        lambda *_a, **_k: _FakeResponse(payload))
    has_update, tag, url, _ = updater.check_update()
    assert has_update is True and tag == "v9.9.9" and url == "https://x/exe"


def test_download_update_short_circuits_outside_frozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert updater.download_update("https://x/exe") is None


def test_install_writes_backup_and_rollback(tmp_path, monkeypatch):
    """生成的 bat 必须留 .bak 且在覆盖失败时回滚；同时真实产出备份文件。

    启动 bat 改走 `proc_hidden.popen_hidden(["cmd", "/c", bat])`：GUI 子系统没有
    控制台，os.startfile 一个 .bat 会亮出黑色 cmd 窗口并停留几秒（替换 exe 期间
    用户正盯着屏幕）。这里断言「用 cmd 执行 bat」而不是「startfile」。
    """
    fake_exe = tmp_path / "goldenhandmaidens.exe"
    fake_exe.write_bytes(b"original")
    new_file = tmp_path / "goldenhandmaidens.exe.new"
    new_file.write_bytes(b"x" * (updater.MIN_EXE_SIZE + 1))

    started = []
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    monkeypatch.setattr(updater, "popen_hidden", lambda cmd: started.append(cmd))

    with pytest.raises(SystemExit):
        updater.install_and_restart(str(new_file))

    assert (tmp_path / "goldenhandmaidens.exe.bak").read_bytes() == b"original"
    bat = (tmp_path / "update.bat").read_text()
    assert 'set "BAK=' in bat
    assert 'move /y "%BAK%" "%EXE%"' in bat
    assert ":fail" in bat
    assert len(started) == 1
    assert started[0][:2] == ["cmd", "/c"] and started[0][2].endswith("update.bat")
