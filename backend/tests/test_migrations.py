"""013-I00：轻量迁移机制。"""

import pytest
from sqlalchemy import inspect as sa_inspect

from db_migrate import (
    MigrationError,
    applied_migrations,
    current_version,
    init_db,
    make_engine,
    run_migrations,
)


def _columns(engine, table: str) -> set[str]:
    return {col["name"] for col in sa_inspect(engine).get_columns(table)}


def test_init_creates_tables_and_applies_migrations(tmp_path):
    engine = make_engine(tmp_path / "t.db")
    init_db(engine)

    tables = set(sa_inspect(engine).get_table_names())
    # 业务表
    assert {"product", "order", "suborder", "purchaseorder", "pricesnapshot"} <= tables
    # 检测表
    assert {
        "inspection_run",
        "item_snapshot",
        "assertion_result",
        "metric",
        "score",
        "inspection_report",
    } <= tables
    # 迁移版本
    assert current_version(engine) == 1
    assert [row[1] for row in applied_migrations(engine)] == ["001_add_store_column.sql"]
    # store 列由迁移保证存在
    assert "store" in _columns(engine, "product")


def test_migrations_are_idempotent(tmp_path):
    engine = make_engine(tmp_path / "t.db")
    init_db(engine)

    assert run_migrations(engine) == []          # 第二次无待应用
    init_db(engine)                              # 重复初始化不报错
    assert current_version(engine) == 1
    assert len(applied_migrations(engine)) == 1


def test_ensure_column_on_missing_table_raises(tmp_path):
    migrations = tmp_path / "mig"
    migrations.mkdir()
    (migrations / "001_bad.sql").write_text(
        "-- @ensure-column nosuchtable.anything INTEGER\n", encoding="utf-8"
    )

    engine = make_engine(tmp_path / "t.db")
    with pytest.raises(MigrationError):
        run_migrations(engine, migrations)
    assert current_version(engine) == 0


def test_bad_sql_raises_and_does_not_record_version(tmp_path):
    """语句报错必须抛出 MigrationError，且不写入 schema_version。

    注意：SQLite（pysqlite）不在事务里保护 DDL，`CREATE TABLE` 即使后续语句报错
    也不会回滚。因此迁移文件必须自身幂等（IF NOT EXISTS / @ensure-column），
    修复后可以直接重跑。
    """
    migrations = tmp_path / "mig"
    migrations.mkdir()
    (migrations / "001_bad.sql").write_text(
        "CREATE TABLE IF NOT EXISTS should_stay (id INTEGER);\nSELEC nonsense;\n",
        encoding="utf-8",
    )

    engine = make_engine(tmp_path / "t.db")
    with pytest.raises(MigrationError):
        run_migrations(engine, migrations)

    assert current_version(engine) == 0
    assert applied_migrations(engine) == []

    # 文件被移走后，重跑应当成功（version 从未记录过）
    (migrations / "001_bad.sql").write_text(
        "CREATE TABLE IF NOT EXISTS should_stay (id INTEGER);\n", encoding="utf-8"
    )
    assert run_migrations(engine, migrations) == ["001_bad.sql"]


def test_unterminated_statement_raises(tmp_path):
    migrations = tmp_path / "mig"
    migrations.mkdir()
    (migrations / "001_bad.sql").write_text(
        "CREATE TABLE no_semicolon (id INTEGER)\n", encoding="utf-8"
    )

    engine = make_engine(tmp_path / "t.db")
    with pytest.raises(MigrationError):
        run_migrations(engine, migrations)


def test_bad_filename_raises(tmp_path):
    migrations = tmp_path / "mig"
    migrations.mkdir()
    (migrations / "addstore.sql").write_text("-- noop\n", encoding="utf-8")

    engine = make_engine(tmp_path / "t.db")
    with pytest.raises(MigrationError):
        run_migrations(engine, migrations)
