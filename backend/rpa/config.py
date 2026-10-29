from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录 = backend/ 的上一级（.env 位于项目根）
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(_BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def _detect_system_browser() -> tuple[str, Path] | tuple[None, None]:
    """自动探测系统安装的浏览器，返回 (Playwright channel, 用户数据目录)。

    Windows 上优先 Edge（系统自带），其次 Chrome。
    """
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        ("msedge", local / "Microsoft" / "Edge" / "User Data"),
        ("chrome", local / "Google" / "Chrome" / "User Data"),
    ]
    for channel, profile in candidates:
        if profile.is_dir():
            return channel, profile
    return None, None


@dataclass(frozen=True)
class RPAConfig:
    base_dir: Path
    master_key: str
    headless: bool
    browser_data_dir: Path
    chromium_path: str
    task_timeout: int
    delay_min: float
    delay_max: float
    verify_timeout: int
    screenshot_dir: Path
    debug_screenshot: bool
    qianniu_finance_url: str
    qianniu_trade_url: str
    # 浏览器模式：
    #   isolated = 每个账号独立 profile（默认，登录态互不污染）
    #   system   = 直接使用系统浏览器（Edge/Chrome）的真实 profile，
    #              复用你日常浏览器的登录态；要求该浏览器已完全关闭
    #   cdp      = 连接一个已经以 --remote-debugging-port 启动的浏览器，
    #              直接驱动当前打开的浏览器（不新开窗口）
    browser_mode: str
    cdp_endpoint: str
    system_profile_dir: Path | None
    browser_channel: str

    def browser_profile_dir(self, account_id: int) -> Path:
        """每个账号独立的浏览器用户数据目录，登录态互不污染。"""
        path = self.browser_data_dir / f"account-{account_id}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_dirs(self) -> None:
        self.browser_data_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)


_DETECTED_CHANNEL, _DETECTED_PROFILE = _detect_system_browser()

rpa_config = RPAConfig(
    base_dir=_BASE_DIR,
    master_key=os.getenv("RPA_MASTER_KEY", "").strip(),
    headless=_bool("RPA_HEADLESS", False),
    browser_data_dir=_BASE_DIR / os.getenv("RPA_BROWSER_DATA_DIR", "./browser_data").lstrip("./"),
    chromium_path=os.getenv("RPA_CHROMIUM_PATH", "").strip(),
    task_timeout=_int("RPA_TASK_TIMEOUT", 600),
    delay_min=_float("RPA_DELAY_MIN", 1.0),
    delay_max=_float("RPA_DELAY_MAX", 2.5),
    verify_timeout=_int("RPA_VERIFY_TIMEOUT", 300),
    screenshot_dir=_BASE_DIR / os.getenv("RPA_SCREENSHOT_DIR", "./rpa_screenshots").lstrip("./"),
    debug_screenshot=_bool("RPA_DEBUG_SCREENSHOT", False),
    # 千牛网页版（work.taobao.com）财务 / 交易页直链。
    # 工作台为登录后渲染的 SPA，子页面 URL 不固定；登录后从地址栏复制真实 URL 填到 .env，
    # 未配置时回退为「进入工作台首页后点击左侧导航菜单」。
    qianniu_finance_url=os.getenv("RPA_QIANNIU_FINANCE_URL", "").strip(),
    qianniu_trade_url=os.getenv("RPA_QIANNIU_TRADE_URL", "").strip(),
    browser_mode=os.getenv("RPA_BROWSER_MODE", "isolated").strip().lower() or "isolated",
    cdp_endpoint=os.getenv("RPA_CDP_ENDPOINT", "http://127.0.0.1:9222").strip(),
    system_profile_dir=(
        Path(os.getenv("RPA_SYSTEM_PROFILE_DIR", "").strip()) if os.getenv("RPA_SYSTEM_PROFILE_DIR", "").strip()
        else _DETECTED_PROFILE
    ),
    browser_channel=(
        os.getenv("RPA_BROWSER_CHANNEL", "").strip() or _DETECTED_CHANNEL or "msedge"
    ),
)
