"""阿里妈妈投放后台数据抓取。

抓取的数据集（与千牛共用同一套登录账号，用户可分别勾选）：
    promotion_ztc             直通车花费
    promotion_mofang          引力魔方花费
    promotion_wanxiangtai     万相台花费
    promotion_other           其它推广（淘宝客 / 超级推荐等）

每条抓取结果以 `{"category", "sub_category", "month", "amount"}` 形式返回，
由 runner 写入 `StorePlatformExpense` 表。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Iterable

from rpa.browser import BrowserSession, NeedManualVerification, ScrapeError
from rpa.selectors import ALIMAMA

# 数据集 → (阿里妈妈页面 URL, 展示名称)
_DATASET_PAGES: dict[str, tuple[str, str]] = {
    "promotion_ztc": (ALIMAMA["zhitongche"], "直通车"),
    "promotion_mofang": (ALIMAMA["mofang"], "引力魔方"),
    "promotion_wanxiangtai": (ALIMAMA["wanxiangtai"], "万相台"),
    "promotion_other": (ALIMAMA["home"], "其它推广"),
}

SUPPORTED_DATASETS = tuple(_DATASET_PAGES.keys())


@dataclass
class ExpenseRecord:
    category: str
    sub_category: str
    month: str
    amount: float
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "sub_category": self.sub_category,
            "month": self.month,
            "amount": self.amount,
            "note": self.note,
        }


@dataclass
class AlimamaResult:
    records: list[ExpenseRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _page_month(page) -> str | None:
    """读取页面文本识别账期月份；SPA 渲染慢，取不到就等待重试。"""
    for attempt in range(3):
        try:
            body = page.inner_text("body", timeout=5000)
        except Exception:  # noqa: BLE001
            body = ""
        m = re.search(r"(20\d{2})[-年/.]\s*(\d{1,2})", body[:4000])
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}"
        if attempt < 2:
            time.sleep(2.0)
    return None


def scrape(
    session: BrowserSession,
    datasets: Iterable[str],
    username: str,
    password: str,
    store: int,
) -> AlimamaResult:
    """执行阿里妈妈抓取，返回结构化推广费用记录。"""
    requested = [d for d in datasets if d in SUPPORTED_DATASETS]
    if not requested:
        raise ScrapeError(f"未选择任何阿里妈妈数据集，可选：{SUPPORTED_DATASETS}")

    result = AlimamaResult()

    # ── 登录（与千牛同一套账号体系） ────────────────────────────
    if not session.is_logged_in(ALIMAMA["home"]):
        try:
            session.login(username, password, ALIMAMA["home"])
        except NeedManualVerification as exc:
            session.wait_for_manual_verification(exc.reason)
        # 登录后复核并完成 SSO 授权链，避免「登录成功后又回到登录页」
        if not session.ensure_logged_in(ALIMAMA["home"]):
            session.screenshot("alimama-login-failed")
            raise ScrapeError(
                "阿里妈妈登录失败（账号密码错误、未完成验证或 SSO 授权未完成）。"
                "请检查账号凭据，或在弹出的浏览器窗口中手动登录后重试。"
            )

    for dataset in requested:
        url, display_name = _DATASET_PAGES[dataset]
        session.goto(url)
        session.close_popups()
        session.human_delay(2.0, 4.0)

        month = _page_month(session.page)
        if not month:
            result.warnings.append(
                f"未能从「{display_name}」页面识别账期月份，已跳过该数据集。"
            )
            session.screenshot(f"alimama-month-unknown-{dataset}")
            continue

        # 依次尝试按关键词提取，取第一个有效值
        amount = None
        for hint in ("花费", "消耗", "总花费", "消费", "支出"):
            amount = session.extract_page_amount(hint_text=hint)
            if amount is not None:
                break
        if amount is None:
            amount = session.extract_page_amount()

        if amount is None:
            result.warnings.append(
                f"未能从「{display_name}」页面提取花费金额，可能页面已改版。"
                "请检查 rpa/selectors.py，或改为手动录入该月推广费。"
            )
            session.screenshot(f"alimama-missing-{dataset}")
            continue

        result.records.append(
            ExpenseRecord(
                category="promotion",
                sub_category=display_name,
                month=month,
                amount=amount,
                note=f"RPA 自动抓取（阿里妈妈-{display_name}）",
            )
        )
        session.log(f"抓到 {display_name}花费（{month}）：¥{amount:.2f}")

    return result
