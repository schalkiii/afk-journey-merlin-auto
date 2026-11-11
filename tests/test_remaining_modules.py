"""补齐此前测试全文未提及的模块：拖拽 IPC、阵容配置、商城/邮件/挂机入口决策。

负验证留痕：
- 把 `check_current_state` 的优先级顺序倒过来，`test_state_priority_prefers_highest_paid_state` 必须失败；
- 删掉 `shangcheng.main()` 里第 2 步的失败返回，`test_shop_aborts_when_second_entry_missing` 必须失败；
- 把 `deploy_formation` 的配置存在性检查删掉，`test_deploy_formation_missing_config` 必须失败。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import drag_utils
import formation
import hero_metadata
import meirirenwulingqu
import shangcheng
import shouquguajijiangli
import version
import youyishangcheng


class _FakeTime:
    def __init__(self):
        self.elapsed = 0.0

    def sleep(self, seconds):
        self.elapsed += seconds

    def time(self):
        return self.elapsed


@pytest.fixture
def stub_clock(monkeypatch):
    for module in (meirirenwulingqu, shangcheng, youyishangcheng, shouquguajijiangli):
        monkeypatch.setattr(module, "time", _FakeTime())
        monkeypatch.setattr(module, "check_stop", lambda: None, raising=False)
    return monkeypatch


def test_send_drag_writes_coordinates(tmp_path, monkeypatch):
    path = tmp_path / "drag_coord.txt"
    monkeypatch.setattr(drag_utils, "DRAG_COORD_PATH", str(path))
    drag_utils.send_drag(10, 20, 30, 40)
    assert path.read_text(encoding="utf-8") == "10 20 30 40"
    drag_utils.send_drag(1, 2, 3, 4, hold_ms=500)
    assert path.read_text(encoding="utf-8") == "1 2 3 4 500"


def test_wait_for_drag_complete_returns_true_when_file_gone(tmp_path, monkeypatch):
    monkeypatch.setattr(drag_utils, "DRAG_COORD_PATH", str(tmp_path / "absent.txt"))
    monkeypatch.setattr(drag_utils, "check_stop", lambda: None, raising=False)
    assert drag_utils.wait_for_drag_complete(check_interval=0.01, timeout=0.1) is True


def test_wait_for_drag_complete_times_out(tmp_path, monkeypatch):
    path = tmp_path / "drag_coord.txt"
    path.write_text("1 2 3 4", encoding="utf-8")
    monkeypatch.setattr(drag_utils, "DRAG_COORD_PATH", str(path))
    monkeypatch.setattr(drag_utils, "check_stop", lambda: None, raising=False)
    assert drag_utils.wait_for_drag_complete(check_interval=0.05, timeout=0.1) is False


def test_state_priority_prefers_highest_paid_state(monkeypatch):
    """付费 2 次与免费 3 次同时可见时，必须按高优先级返回付费 2 次。"""
    def fake_find_center(path, *_args, **_kwargs):
        name = os.path.basename(path)
        return (1, 1) if name in ("shalou1.png", "shalou6.png") else None

    monkeypatch.setattr(shouquguajijiangli, "find_center", fake_find_center)
    assert shouquguajijiangli.check_current_state() == shouquguajijiangli.STATE_PAID_2


def test_shop_aborts_when_second_entry_missing(stub_clock):
    calls = []

    def fake_wait(path, *_args, **_kwargs):
        calls.append(os.path.basename(path))
        return os.path.basename(path) == "shenmiwu.png"

    stub_clock.setattr(shangcheng, "wait_and_click", fake_wait)
    assert shangcheng.main() is False
    assert calls == ["shenmiwu.png", "shangdian.png"]


def test_shop_runs_friend_shop_when_entries_present(stub_clock):
    friend_calls = []
    stub_clock.setattr(shangcheng, "wait_and_click", lambda *_a, **_k: True)
    stub_clock.setattr(youyishangcheng, "main", lambda: friend_calls.append(True))
    assert shangcheng.main() is True
    assert friend_calls == [True]


def test_friend_shop_stops_on_first_missing_entry(stub_clock):
    calls = []

    def fake_wait(path, *_args, **_kwargs):
        calls.append(os.path.basename(path))
        return False

    stub_clock.setattr(youyishangcheng, "wait_and_click", fake_wait)
    youyishangcheng.main()
    assert calls == ["youyishangdian.png"]


def test_daily_task_aborts_when_menu_missing(stub_clock):
    stub_clock.setattr(meirirenwulingqu, "wait_and_click", lambda *_a, **_k: False)
    assert meirirenwulingqu.main() is False


def test_deploy_formation_missing_config(tmp_path, monkeypatch):
    monkeypatch.setattr(formation, "get_config_path", lambda _name: str(tmp_path / "absent.json"))
    assert formation.deploy_formation("任意阵容", {}) is False


def test_deploy_formation_unknown_name(tmp_path, monkeypatch):
    cfg = tmp_path / "formations.json"
    cfg.write_text(json.dumps({"已知阵容": {"map": "m1", "steps": []}}), encoding="utf-8")
    monkeypatch.setattr(formation, "get_config_path", lambda _name: str(cfg))
    assert formation.deploy_formation("不存在的阵容", {}) is False


def test_deploy_formation_missing_anchor(tmp_path, monkeypatch):
    cfg = tmp_path / "formations.json"
    cfg.write_text(json.dumps({"已知阵容": {"map": "m1", "steps": []}}), encoding="utf-8")
    monkeypatch.setattr(formation, "get_config_path", lambda _name: str(cfg))
    monkeypatch.setattr(formation, "find_center", lambda *_a, **_k: None)
    assert formation.deploy_formation("已知阵容", {}) is False


def test_hero_metadata_race_and_job_names_are_consistent():
    """元数据表的缩写键必须都能在中文名表里查到，否则日志与筛选会漏项。"""
    assert set(hero_metadata.RACE_NAMES) >= {code for code in hero_metadata.HERO_RACE.values()}
    assert set(hero_metadata.JOB_NAMES) >= {code for code in hero_metadata.HERO_JOB.values()}


def test_version_is_a_semver_tag():
    import re

    assert re.fullmatch(r"v\d+\.\d+\.\d+", version.__version__)
