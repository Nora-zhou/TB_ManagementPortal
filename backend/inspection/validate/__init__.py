"""013-I02：断言层。

对外只暴露 `run_assertions(data)`：
输入展示结构（`to_display()` / `from_parse()` 的返回值），输出断言表。
"""

from inspection.validate.rules import run_assertions, load_thresholds

__all__ = ["run_assertions", "load_thresholds"]
