"""轻量 SQL 迁移：编号文件 + schema_version 表。

设计边界（很重要）：
- **建表**由 `SQLModel.metadata.create_all()` 负责，ORM 定义是唯一口径，
  迁移文件里不重复写 CREATE TABLE，避免 SQL 与模型定义漂移。
- **迁移文件只处理 create_all 做不到的事**：给已有表加列 / 加索引 / 回填数据。
- SQLite 不支持 `ADD COLUMN IF NOT EXISTS`，所以用指令注释声明「确保某列存在」：

      -- @ensure-column product.store INTEGER DEFAULT 1

  执行器先查 `PRAGMA table_info`，缺列才发 ALTER，因此每个迁移天然幂等。

失败策略：任何语句报错都抛 `MigrationError`（带文件名与行号），且不写入
schema_version，不再像旧的 `ALTER TABLE ... except: pass` 那样静默跳过。

已知限制：SQLite（pysqlite）不在事务中保护 DDL，`CREATE TABLE` 等语句即使后续
语句失败也不会回滚。因此每个迁移文件必须自身幂等（`IF NOT EXISTS` /
`@ensure-column`），修好之后可以直接重跑。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from sqlalchemy import Engine, text
from sqlalchemy.engine import URL
from sqlmodel import SQLModel, create_engine

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_VERSION_RE = re.compile(r"^(\d+)_.*\.sql$")
_ENSURE_COLUMN_RE = re.compile(
    r"^--\s*@ensure-column\s+([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s+(.+)$"
)

_CREATE_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    filename   TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


class MigrationError(RuntimeError):
    """迁移执行失败（语句报错、目标表不存在、语句未以分号结尾等）。"""


def make_engine(db_path: Union[str, Path]) -> Engine:
    """按文件路径建 SQLite 引擎（URL.create 负责 Windows 路径与空格转义）。"""
    url = URL.create("sqlite", database=str(Path(db_path)))
    return create_engine(url, connect_args={"check_same_thread": False})


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f'PRAGMA table_info("{table}")')).fetchall()
    return {row[1] for row in rows}


def _apply_sql_file(conn, path: Path) -> None:
    """逐行解析并执行一个迁移文件；支持 @ensure-column 指令。"""
    buffer: list[str] = []

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue

        match = _ENSURE_COLUMN_RE.match(line)
        if match:
            if buffer:
                raise MigrationError(f"{path.name}:{lineno} 上一条语句未以分号结尾")
            table, column, definition = match.group(1), match.group(2), match.group(3).strip()
            columns = _table_columns(conn, table)
            if not columns:
                raise MigrationError(
                    f"{path.name}:{lineno} 表 {table} 不存在，无法确保列 {column}"
                )
            if column not in columns:
                conn.execute(
                    text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')
                )
            continue

        if line.startswith("--"):
            continue

        buffer.append(raw)
        if line.endswith(";"):
            statement = "\n".join(buffer).strip().rstrip(";").strip()
            buffer.clear()
            if statement:
                conn.execute(text(statement))

    if buffer:
        raise MigrationError(f"{path.name}: 文件末尾有未以分号结尾的语句")


def run_migrations(engine: Engine, migrations_dir: Union[str, Path, None] = None) -> list[str]:
    """按编号顺序执行未应用的迁移，返回本次新应用的文件名列表。"""
    directory = Path(migrations_dir) if migrations_dir else MIGRATIONS_DIR
    if not directory.is_dir():
        return []

    with engine.begin() as conn:
        conn.execute(text(_CREATE_VERSION_TABLE))
        applied = {
            row[0]
            for row in conn.execute(text("SELECT version FROM schema_version")).fetchall()
        }

    newly_applied: list[str] = []
    for path in sorted(directory.glob("*.sql")):
        match = _VERSION_RE.match(path.name)
        if not match:
            raise MigrationError(f"{path.name} 命名不符合 <编号>_<描述>.sql")
        version = int(match.group(1))
        if version in applied:
            continue

        try:
            with engine.begin() as conn:
                _apply_sql_file(conn, path)
                conn.execute(
                    text(
                        "INSERT INTO schema_version (version, filename, applied_at) "
                        "VALUES (:version, :filename, :applied_at)"
                    ),
                    {
                        "version": version,
                        "filename": path.name,
                        "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    },
                )
        except MigrationError:
            raise
        except Exception as exc:  # noqa: BLE001 — 统一包装成 MigrationError
            raise MigrationError(f"{path.name} 执行失败：{exc}") from exc

        newly_applied.append(path.name)

    return newly_applied


def applied_migrations(engine: Engine) -> list[tuple[int, str, str]]:
    """已应用的迁移 [(version, filename, applied_at)]；表不存在时返回空列表。"""
    with engine.connect() as conn:
        try:
            rows = conn.execute(
                text(
                    "SELECT version, filename, applied_at FROM schema_version "
                    "ORDER BY version"
                )
            ).fetchall()
        except Exception:  # noqa: BLE001 — 未初始化过迁移的库
            return []
    return [(row[0], row[1], row[2]) for row in rows]


def current_version(engine: Engine) -> int:
    rows = applied_migrations(engine)
    return rows[-1][0] if rows else 0


def init_db(engine: Engine) -> list[str]:
    """建表 + 跑迁移。服务启动与 CLI `init` 共用这一条路径。"""
    import models  # noqa: F401 — 注册 11 张业务表
    import inspection.models  # noqa: F401 — 注册 6 张检测表

    SQLModel.metadata.create_all(engine)
    return run_migrations(engine)
