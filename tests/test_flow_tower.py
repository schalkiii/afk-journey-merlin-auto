"""爬塔仓库练度文本解析 `_load_warehouse_levels` 的契约测试。

全为纯文本解析、零外部依赖：只把 `WAREHOUSE_TXT_PATH` 指到 tmp_path 下的文件，
不触碰截图/模板匹配/点击，也不依赖真实仓库扫描结果。
"""
import flow_tower


def test_missing_warehouse_file_returns_empty_dict(monkeypatch, tmp_path):
    """文件不存在时返回空字典（调用方据此视为全部未拥有），绝不能抛异常中断爬塔。"""
    missing = tmp_path / "not_created.txt"
    monkeypatch.setattr(flow_tower, "WAREHOUSE_TXT_PATH", missing)

    assert flow_tower._load_warehouse_levels() == {}


def test_normal_lines_parsed_into_dict(monkeypatch, tmp_path):
    """正常两行「名字,档位」解析成字典。"""
    warehouse = tmp_path / "x.txt"
    warehouse.write_text("gubian,高\nmeimo,低\n", encoding="utf-8")
    monkeypatch.setattr(flow_tower, "WAREHOUSE_TXT_PATH", warehouse)

    assert flow_tower._load_warehouse_levels() == {"gubian": "高", "meimo": "低"}


def test_blank_and_commaless_lines_are_skipped(monkeypatch, tmp_path):
    """空行、纯空白行、不含逗号的脏行混在正常行之间时必须被跳过而不是报错或入库。"""
    warehouse = tmp_path / "x.txt"
    warehouse.write_text(
        "gubian,高\n"
        "\n"
        "   \t \n"
        "这是扫描器输出的表头没有逗号\n"
        "meimo,低\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(flow_tower, "WAREHOUSE_TXT_PATH", warehouse)

    assert flow_tower._load_warehouse_levels() == {"gubian": "高", "meimo": "低"}


def test_only_first_comma_is_the_separator(monkeypatch, tmp_path):
    """`split(",", 1)` 的语义：仅第一个逗号作分隔，值里余下逗号原样留在档位字符串里。

    这是刻意的一次性切分（避免名字/档位里带逗号时整行崩掉），此用例如实锁住该行为。
    """
    warehouse = tmp_path / "x.txt"
    warehouse.write_text("gubian,高,额外\n", encoding="utf-8")
    monkeypatch.setattr(flow_tower, "WAREHOUSE_TXT_PATH", warehouse)

    assert flow_tower._load_warehouse_levels() == {"gubian": "高,额外"}


def test_name_and_level_are_stripped(monkeypatch, tmp_path):
    """名字与档位两侧空白（含制表符）被 strip，避免同名条目因空格差异判成两个英雄。"""
    warehouse = tmp_path / "x.txt"
    warehouse.write_text("  gubian \t,\t 高 \n", encoding="utf-8")
    monkeypatch.setattr(flow_tower, "WAREHOUSE_TXT_PATH", warehouse)

    assert flow_tower._load_warehouse_levels() == {"gubian": "高"}
