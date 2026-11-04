"""GUI 测试共用夹具。

同一进程内反复创建/销毁 Tk 根会随机抛 TclError（实测会让用例间歇性 skip），
所以整个测试会话只建一个隐藏的根，各 GUI 测试模块复用它。
测试会话还会把 `game_bot.log` 的写入路径整体挪到临时目录，避免污染用户日志。
"""
import pytest


@pytest.fixture(scope="session", autouse=True)
def isolate_product_log(tmp_path_factory):
    """把日志写入重定向到临时目录，测试不许碰用户真正用来调试的 game_bot.log。

    实测一次 pytest 会往项目根 game_bot.log 追加 10 行「已注册全局热键」——GUI 构造期
    的 `log()` 早于各测试自己打的 log 补丁，走的是模块级 LOG_FILE。跑了三十轮之后
    这行噪声在用户日志里累积到 300 条，把真正有用的识别/领取记录埋掉了。
    """
    import bot_runtime

    real_log = bot_runtime.LOG_FILE
    bot_runtime.LOG_FILE = str(tmp_path_factory.mktemp("bot-log") / "game_bot.log")
    try:
        yield
    finally:
        bot_runtime.LOG_FILE = real_log


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
