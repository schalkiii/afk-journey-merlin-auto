"""爬塔起始界面恢复：任务可能从上个任务的子页开始，先回主界面再点玩法目录。

今日日志证据：`exit` 15 秒未出现、随后 `pata` 15 秒未出现——流程从子页开始，
子页底部同样有 wanfamulu 图标，直接点击会被误判成功，之后找不到 pata。
"""
import time
import types

import jiance
import pata


def _run_flow(monkeypatch, recover_result):
    """驱动 flow_pata：桩掉所有点击、识别与等待，塔列表全部跳过。

    2026-11-08 起「天穹试炼」卡片改用模板匹配 + 滚动重试（卡片在列表下方），
    不再走 wait_and_click("pata")；这里让卡片模板命中并记 send_coord 事件。
    """
    events = []
    libao_calls = []

    def fake_wait_and_click(template_path, name, *args, **kwargs):
        events.append(name)
        return True

    def fake_recover(*args, **kwargs):
        events.append("recover")
        return recover_result

    def fake_find(template_path, *args, **kwargs):
        return (3000, 400) if template_path == pata.tpl_pata else None

    monkeypatch.setattr(pata, "recover_to_main_interface", fake_recover)
    monkeypatch.setattr(pata, "wait_and_click", fake_wait_and_click)
    # 进玩法目录已收敛到 common.open_wanfamulu（点后确认目录标题）；这里用同名事件记账，
    # 保持「恢复 → 玩法目录 → 卡片 → 退出」的顺序断言不变。
    monkeypatch.setattr(pata, "open_wanfamulu",
                        lambda *args, **kwargs: (events.append("wanfamulu"), True)[1])
    monkeypatch.setattr(pata, "find_center_silent", fake_find)
    monkeypatch.setattr(pata, "scroll_in_client_region", lambda *a, **k: True)
    # 2026-11-10：卡片点击改走 click_and_confirm（点击后校验是否离开玩法目录）
    monkeypatch.setattr(pata, "click_and_confirm",
                        lambda *args, **kwargs: (events.append("pata-click"), True)[1])
    monkeypatch.setattr(pata, "random_sleep", lambda: None)
    monkeypatch.setattr(pata, "time", types.SimpleNamespace(time=time.time,
                                                            sleep=lambda _seconds: None))
    monkeypatch.setattr(jiance, "check_and_handle_libao",
                        lambda *args, **kwargs: libao_calls.append(True))
    return events, libao_calls


def test_flow_pata_recovers_main_interface_before_wanfamulu(monkeypatch):
    """恢复必须发生在点 wanfamulu 之前，之后照原流程进入 pata 并退出。"""
    events, libao_calls = _run_flow(monkeypatch, recover_result=True)

    assert pata.flow_pata() is True
    assert events == ["recover", "wanfamulu", "pata-click", "exit"]
    assert libao_calls == [True]


def test_flow_pata_continues_when_recovery_fails(monkeypatch):
    """恢复失败不新增失败语义：仍继续原流程（点 wanfamulu → pata → exit）。"""
    events, _libao_calls = _run_flow(monkeypatch, recover_result=False)

    assert pata.flow_pata() is True
    assert events == ["recover", "wanfamulu", "pata-click", "exit"]
