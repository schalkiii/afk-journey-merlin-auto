"""成品移到 dist/ 后，数据目录必须仍在仓库根（不丢配置、不分裂日志与坐标 IPC）。

负验证：删掉 `get_work_path` 里的 dist 分支，
`test_frozen_in_dist_keeps_data_at_repo_root` 必须失败。
"""

import os
import sys

import common


def test_frozen_in_dist_keeps_data_at_repo_root(monkeypatch, tmp_path):
    """exe 在 dist/、上级有配置 → 配置/日志/shared 全部落在上级。"""
    repo = tmp_path / "repo"
    dist = repo / "dist"
    dist.mkdir(parents=True)
    (repo / "game_bot_config.json").write_text("{}", encoding="utf-8")
    exe = dist / "goldenhandmaidens.exe"

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe), raising=False)

    assert common.get_work_path("game_bot_config.json") == str(repo / "game_bot_config.json")
    assert common.get_work_path("game_bot.log") == str(repo / "game_bot.log")
    assert common.get_work_path(os.path.join("shared", "target_coord.txt")) == str(
        repo / "shared" / "target_coord.txt")


def test_frozen_in_dist_without_parent_config_stays_portable(monkeypatch, tmp_path):
    """把 dist/ 单独拷到别处（上级无配置）→ 回退到 exe 同目录，保持便携。"""
    dist = tmp_path / "dist"
    dist.mkdir()
    exe = dist / "goldenhandmaidens.exe"

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe), raising=False)

    assert common.get_work_path("game_bot_config.json") == str(dist / "game_bot_config.json")


def test_frozen_outside_dist_uses_exe_dir(monkeypatch, tmp_path):
    """exe 不在 dist/（例如旧布局放仓库根）→ 沿用原有 exe 同目录行为。"""
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    (tmp_path / "game_bot_config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "goldenhandmaidens.exe"),
                        raising=False)

    assert common.get_work_path("game_bot_config.json") == str(
        exe_dir / "game_bot_config.json")


def test_source_run_uses_module_dir(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert common.get_work_path("x.txt") == os.path.join(
        os.path.dirname(common.__file__), "x.txt")
