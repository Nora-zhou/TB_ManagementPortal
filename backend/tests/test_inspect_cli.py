"""013-I00：inspect_cli 骨架。"""

import pytest

from db_migrate import init_db, make_engine
from inspect_cli import main


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "013-store-inspection 0.1.0" in capsys.readouterr().out


def test_doctor_passes_after_init(tmp_path, capsys):
    db = tmp_path / "t.db"
    init_db(make_engine(db))

    assert main(["--db", str(db), "doctor"]) == 0
    out = capsys.readouterr().out
    assert "inspection" in out
    assert "6/6 就绪" in out


def test_doctor_on_empty_db_warns_but_passes(tmp_path, capsys):
    # 空库只产生 WARN，不算失败
    assert main(["--db", str(tmp_path / "empty.db"), "doctor"]) == 0
    assert "尚未初始化" in capsys.readouterr().out


def test_init_command_creates_tables(tmp_path, capsys):
    db = tmp_path / "t.db"
    assert main(["--db", str(db), "init"]) == 0
    out = capsys.readouterr().out
    assert "001_add_store_column" in out
    assert "tables" in out


def test_pending_command_returns_3(capsys):
    assert main(["collect", "--item", "123456"]) == 3
    assert "尚未实现" in capsys.readouterr().out


def test_unknown_command_exits_2():
    with pytest.raises(SystemExit) as exc:
        main(["bogus"])
    assert exc.value.code == 2
