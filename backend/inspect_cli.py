"""013 检测模块命令行入口（不依赖 FastAPI）。

用法：
    python inspect_cli.py --version
    python inspect_cli.py doctor            # 自检：库 / 迁移 / 表 / Playwright / raw 目录
    python inspect_cli.py init              # 建表 + 跑迁移（等价于启动服务时的初始化）
    python inspect_cli.py collect --item <id>   # I01 起逐步实现

I00 阶段只有 doctor / init 可用，其余子命令是占位骨架（退出码 3）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import inspect as sa_inspect

from db_migrate import MigrationError, applied_migrations, init_db, make_engine
from rpa.logging_utils import configure_stdout, safe_print

FEATURE = "013-store-inspection"
VERSION = "0.1.0"

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BACKEND_DIR / "tasks.db"
RAW_DIR = BACKEND_DIR.parent / "data" / "raw"

INSPECTION_TABLES = (
    "inspection_run",
    "item_snapshot",
    "assertion_result",
    "metric",
    "score",
    "inspection_report",
)

# 占位命令 → 计划中实现它的迭代编号
PENDING_COMMANDS: dict[str, str] = {
    "collect": "I01",
    "show": "I03",
    "validate": "I06",
    "analyze": "I07",
    "signals": "I08",
    "score": "I09",
    "report": "I11",
    "diff": "I14",
    "recompute": "I15",
}


def _fmt_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / 1024 / 1024:.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes} B"


def _print_rows(rows: list[tuple[str, str, str]]) -> None:
    width = max(len(name) for _, name, _ in rows) + 2
    for status, name, detail in rows:
        safe_print(f"  {status:<5}{name:<{width}}{detail}")


def _table_names(engine) -> list[str]:
    try:
        return sorted(sa_inspect(engine).get_table_names())
    except Exception:  # noqa: BLE001 — 库文件损坏或不存在
        return []


def _column_count(engine, table: str) -> int:
    try:
        return len(sa_inspect(engine).get_columns(table))
    except Exception:  # noqa: BLE001
        return 0


def cmd_doctor(db_path: Path) -> int:
    safe_print(f"{FEATURE}  doctor  ·  v{VERSION}")
    engine = make_engine(db_path)
    rows: list[tuple[str, str, str]] = []

    exists = db_path.exists()
    size = db_path.stat().st_size if exists else 0
    rows.append(("OK" if exists else "WARN", "db", f"{db_path}  ({_fmt_size(size)})"))

    applied = applied_migrations(engine)
    if applied:
        names = ", ".join(item[1].replace(".sql", "") for item in applied)
        rows.append(("OK", "schema", f"v{applied[-1][0]}  ·  {names}"))
    else:
        rows.append(("WARN", "schema", "尚未初始化（跑 init 或启动一次服务）"))

    tables = _table_names(engine)
    missing_inspection = [t for t in INSPECTION_TABLES if t not in tables]
    inspection_present = [t for t in tables if t in INSPECTION_TABLES]
    business = [t for t in tables if t not in INSPECTION_TABLES and t != "schema_version"]
    infra = 1 if "schema_version" in tables else 0
    rows.append(
        (
            "OK" if tables else "WARN",
            "tables",
            f"共 {len(tables)} 张（业务 {len(business)} / 检测 {len(inspection_present)}"
            f" / 迁移 {infra}）",
        )
    )

    if not missing_inspection and tables:
        cols = _column_count(engine, "item_snapshot")
        rows.append(("OK", "inspection", f"6/6 就绪  ·  item_snapshot {cols} 列"))
    elif not tables:
        rows.append(("WARN", "inspection", "库为空，初始化后再检查"))
    else:
        rows.append(("FAIL", "inspection", f"缺表：{', '.join(missing_inspection)}"))

    try:
        from importlib.metadata import version as pkg_version

        rows.append(("OK", "playwright", pkg_version("playwright")))
    except Exception:  # noqa: BLE001 — 未安装时 I01 无法采集，但不影响 I00
        rows.append(("WARN", "playwright", "未安装（I01 采集需要）"))

    try:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        probe = RAW_DIR / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        rows.append(("OK", "raw_dir", str(RAW_DIR)))
    except Exception as exc:  # noqa: BLE001
        rows.append(("FAIL", "raw_dir", f"不可写：{exc}"))

    _print_rows(rows)
    failed = sum(1 for status, _, _ in rows if status == "FAIL")
    safe_print("")
    safe_print("结果：全部通过" if failed == 0 else f"结果：{failed} 项需要处理")
    return 0 if failed == 0 else 2


def cmd_init(db_path: Path) -> int:
    engine = make_engine(db_path)
    try:
        newly = init_db(engine)
    except MigrationError as exc:
        safe_print(f"[FAIL] 初始化失败：{exc}")
        return 2

    tables = _table_names(engine)
    safe_print(f"db        {db_path}")
    safe_print(f"tables    {len(tables)} 张")
    safe_print(f"migrations {'新应用 ' + ', '.join(newly) if newly else '无待应用'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inspect_cli.py",
        description=f"{FEATURE} · 店铺内容检测模块命令行（v{VERSION}）",
        epilog="I00 阶段只有 doctor / init 可用，其余子命令为占位。",
    )
    parser.add_argument(
        "--version", action="version", version=f"{FEATURE} {VERSION}"
    )
    parser.add_argument(
        "--db", default=str(DEFAULT_DB), help="覆盖数据库文件路径（默认 backend/tasks.db）"
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    sub.add_parser("doctor", help="自检：库 / 迁移 / 表 / Playwright / raw 目录")
    sub.add_parser("init", help="建表并执行增量迁移")

    p = sub.add_parser("collect", help="采集商品或店铺内容")
    p.add_argument("--item", help="商品 ID")
    p.add_argument("--store", help="店铺编号（1/2）")
    p.add_argument("--limit", type=int, help="最多采集多少条")
    p.add_argument("--source", choices=("api", "page"), help="数据源")
    p.add_argument("--verify", action="store_true", help="启用双通道互校")

    p = sub.add_parser("show", help="查看已采集快照")
    p.add_argument("--item", help="商品 ID")
    p.add_argument("--run", help="run_id")

    for name, help_text in (
        ("validate", "运行断言校验"),
        ("analyze", "计算结构指标"),
        ("signals", "输出信号矩阵"),
        ("score", "计算评分卡"),
        ("recompute", "重算历史 run 的判定层"),
    ):
        sub.add_parser(name, help=help_text).add_argument("--run", help="run_id")

    report = sub.add_parser("report", help="生成 HTML / PDF 报告")
    report.add_argument("--run", help="run_id")
    report.add_argument("--pdf", action="store_true", help="同时导出 PDF")

    diff = sub.add_parser("diff", help="两期快照对比")
    diff.add_argument("--run-a", required=True, help="基准 run_id")
    diff.add_argument("--run-b", required=True, help="对比 run_id")

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    db_path = Path(args.db).expanduser().resolve()

    if args.command == "doctor":
        return cmd_doctor(db_path)
    if args.command == "init":
        return cmd_init(db_path)

    iteration = PENDING_COMMANDS.get(args.command, "后续迭代")
    safe_print(
        f"{args.command}：尚未实现（计划在 {iteration} 落地，当前为 I00 骨架）"
    )
    return 3


if __name__ == "__main__":
    sys.exit(main())
