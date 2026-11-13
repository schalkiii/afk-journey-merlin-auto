"""启动期导入回归测试：`updater` 不得在模块顶层导入。

`import Goldenhandmaidens` 是双击 exe 后最先付出的开销，而 updater 只在检查更新 /
下载 / 安装重启时才需要。这里用子进程验证真实导入行为，并用 AST 静态守卫防止
未来有人把局部 import 挪回顶层。两条用例都不创建 Tk 根，可在无图形环境运行。
"""
import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_MODULE = REPO_ROOT / "Goldenhandmaidens.py"

# 局部导入必须出现在这四个更新相关路径中（含方法内后台线程里的嵌套函数）
EXPECTED_IMPORTERS = {
    "GameBotGUI._auto_check_update._check",
    "GameBotGUI._check_update_clicked._check",
    "GameBotGUI._show_update_dialog._download",
    "GameBotGUI._install_and_restart",
}


def test_startup_does_not_import_updater(tmp_path):
    """子进程里导入主模块，`updater` 不应出现在 sys.modules。

    先导入 bot_runtime 并把 LOG_FILE 指到临时目录：否则子进程绕过了
    conftest 的产品日志隔离，启动期任何 print 都会追加到用户的 game_bot.log。
    """
    probe_log = tmp_path / "startup_probe.log"
    code = (
        "import bot_runtime, sys;"
        f"bot_runtime.LOG_FILE = {str(probe_log)!r};"
        "import Goldenhandmaidens;"
        "print('updater' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        # 子进程导入 GUI 主模块时会往 stderr 打中文日志；默认 locale 是 GBK，
        # 用 text=True 不指定编码会让管道读取线程抛 UnicodeDecodeError
        # （pytest 里表现为 PytestUnhandledThreadExceptionWarning）。
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False", (
        f"启动导入不应加载 updater，实际 stdout={result.stdout!r}, stderr={result.stderr!r}"
    )


def _has_direct_updater_import(func_node):
    return any(
        isinstance(stmt, ast.Import) and any(alias.name == "updater" for alias in stmt.names)
        for stmt in func_node.body
    )


def _collect_importers(node, prefix=""):
    """递归收集「函数体内直接写了 import updater」的函数限定名。"""
    names = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = f"{prefix}.{child.name}" if prefix else child.name
            if _has_direct_updater_import(child):
                names.append(qualname)
            names.extend(_collect_importers(child, qualname))
        elif isinstance(child, ast.ClassDef):
            qualname = f"{prefix}.{child.name}" if prefix else child.name
            names.extend(_collect_importers(child, qualname))
        else:
            names.extend(_collect_importers(child, prefix))
    return names


def test_updater_import_is_local_to_update_paths():
    """顶层 import 区不得含 updater；四个使用点必须各自局部导入。"""
    tree = ast.parse(MAIN_MODULE.read_text(encoding="utf-8"))

    top_level_importers = [
        node
        for node in tree.body
        if isinstance(node, ast.Import) and any(alias.name == "updater" for alias in node.names)
    ]
    assert top_level_importers == [], "updater 又被挪回顶层，启动会重新为它付出导入开销"

    importers = set(_collect_importers(tree))
    missing = EXPECTED_IMPORTERS - importers
    assert not missing, f"以下更新路径缺少局部 import updater：{sorted(missing)}"
