"""GUI 测试共用夹具。

同一进程内反复创建/销毁 Tk 根会随机抛 TclError（实测会让用例间歇性 skip），
所以整个测试会话只建一个隐藏的根，各 GUI 测试模块复用它。
"""
import pytest


@pytest.fixture(scope="session")
def tk_root():
    """会话级唯一 Tk 根：不显示窗口，测试结束后统一销毁。"""
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("当前环境没有可用的图形显示，跳过 GUI 测试")
    root.withdraw()
    yield root
    root.destroy()
