"""日志输出工具。

Windows 下后端进程常由桌面启动器 / GUI 拉起，stdout 可能是无效句柄或已关闭的
管道，直接 ``print`` 会抛 ``OSError [Errno 22] Invalid argument``。
本模块统一吞掉输出异常，保证「日志写入数据库」的主流程不受影响。
"""

from __future__ import annotations

import sys


def safe_print(message: str) -> None:
    """打印到 stdout；stdout 不可用时静默忽略，绝不向上抛异常。"""
    try:
        print(message, flush=True)
    except (OSError, ValueError):
        # 无控制台 / 管道已关闭 / 编码失败等情况：忽略即可
        pass


def configure_stdout() -> None:
    """尽力把 stdout 切到 UTF-8，避免中文 / emoji 触发编码错误。"""
    stream = sys.stdout
    if stream is None:
        return
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        pass
