"""013-store-inspection：店铺内容检测模块。

目录约定（随迭代逐步落地）：

    collect/    取数与解析（I01 起）
    validate/   断言层（I06）
    analyze/    指标 / 信号 / 评分 / LLM 归因（I07–I13）
    report/     HTML / PDF 报告（I11–I12）
    runner.py   检测任务执行（I05）
    models.py   6 张表 + 枚举常量

本模块不依赖 FastAPI，可脱离服务端独立运行（入口 backend/inspect_cli.py）。
"""

__all__ = ["models"]
