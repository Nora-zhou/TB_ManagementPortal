"""RPA 子系统：负责登录千牛 / 阿里妈妈并抓取平台费用数据。

模块划分：
    config      — 环境配置加载（.env）
    crypto      — 凭据加解密（Fernet）
    browser     — Playwright 持久化浏览器上下文管理
    selectors   — 各平台页面选择器（集中管理，便于改版后维护）
    qianniu     — 千牛工作台抓取实现
    alimama     — 阿里妈妈投放后台抓取实现
    runner      — 抓取任务执行器（后台线程 + 任务队列）
    logging_utils — Windows 下安全的 stdout 输出
"""

from rpa.config import rpa_config  # noqa: F401

# 预创建浏览器 profile 与截图目录，避免截图时目录不存在
rpa_config.ensure_dirs()
