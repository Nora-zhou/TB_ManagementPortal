"""千牛工作台数据抓取。

抓取的数据集（由用户在创建任务时勾选）：
    platform_fee        平台扣费合计（技术服务费 / 佣金等，来自财务报表）
    shipping_insurance  运费险费用
    order_fee_detail    订单级「卖家服务费」明细（逐条订单）

每条抓取结果以 `{"category", "sub_category", "month", "amount"}` 形式返回，
由 runner 写入 `StorePlatformExpense` 表。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Iterable

from rpa.browser import BrowserSession, NeedManualVerification, ScrapeError
from rpa.config import rpa_config
from rpa.selectors import QIANNIU

# 千牛财务报表中常见的关键词 → (category, sub_category)
_FEE_KEYWORDS: list[tuple[str, str, str]] = [
    # (页面文本关键词, category, sub_category)
    ("技术服务费", "platform_fee", "技术服务费"),
    ("佣金", "platform_fee", "佣金"),
    ("软件服务费", "platform_fee", "软件服务费"),
    ("积分扣款", "platform_fee", "积分返点"),
    ("平台扣费", "platform_fee", "平台扣费合计"),
    ("运费险", "shipping_insurance", "运费险"),
    ("订单险", "shipping_insurance", "订单险"),
    ("退货运费险", "shipping_insurance", "退货运费险"),
]

SUPPORTED_DATASETS = ("platform_fee", "shipping_insurance", "order_fee_detail")


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
class QianniuResult:
    records: list[ExpenseRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _normalize_month(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"(20\d{2})[-年/.]\s*(\d{1,2})", text)
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2)):02d}"


def _page_month(page) -> str | None:
    """读取页面文本识别账期月份；SPA 渲染慢，取不到就等待重试。"""
    for attempt in range(3):
        try:
            body = page.inner_text("body", timeout=5000)
        except Exception:  # noqa: BLE001
            body = ""
        month = _normalize_month(body[:4000])
        if month:
            return month
        if attempt < 2:
            time.sleep(2.0)
    return None


def scrape(
    session: BrowserSession,
    datasets: Iterable[str],
    username: str,
    password: str,
    store: int,
) -> QianniuResult:
    """执行千牛抓取，返回结构化费用记录。"""
    requested = [d for d in datasets if d in SUPPORTED_DATASETS]
    if not requested:
        raise ScrapeError(f"未选择任何千牛数据集，可选：{SUPPORTED_DATASETS}")

    result = QianniuResult()

    # ── 登录 ────────────────────────────────────────────────────
    if not session.is_logged_in(QIANNIU["home"]):
        try:
            session.login(username, password, QIANNIU["home"])
        except NeedManualVerification as exc:
            session.wait_for_manual_verification(exc.reason)
        # 登录/人工验证后复核：SPA 门户未登录时不跳转登录页，
        # 且登录成功后还需走完 SSO 授权链，用 ensure_logged_in 反复导航 +
        # 点授权按钮，避免把「已登录但授权链没走完」误判为登录失败。
        if not session.ensure_logged_in(QIANNIU["home"]):
            session.screenshot("qianniu-login-failed")
            raise ScrapeError(
                "千牛工作台登录失败（账号密码错误、未完成验证或 SSO 授权未完成）。"
                "请检查账号凭据，或在弹出的浏览器窗口中手动登录后重试。"
            )

    # ── 财务报表 ────────────────────────────────────────────────
    if {"platform_fee", "shipping_insurance"} & set(requested):
        session.open_workbench_page(
            rpa_config.qianniu_finance_url,
            QIANNIU["finance_menu_texts"],
            "finance",
            page_label="财务",
        )
        session.close_popups()
        month = _page_month(session.page)
        if not month:
            result.warnings.append(
                "未能从千牛财务报表页面识别账期月份，已跳过自动抓取。"
                "请在页面中确认当前账期后重试，或手动录入该月费用。"
            )
            session.screenshot("qianniu-finance-month-unknown")
            return result

        body_text = _safe_body_text(session.page)
        for keyword, category, sub_category in _FEE_KEYWORDS:
            if category not in requested:
                continue
            amount = _extract_keyword_amount(session, body_text, keyword)
            if amount is None:
                result.warnings.append(
                    f"千牛财务报表中未找到「{keyword}」金额，可能页面已改版。"
                )
                session.screenshot(f"qianniu-missing-{sub_category}")
                continue
            result.records.append(
                ExpenseRecord(
                    category=category,
                    sub_category=sub_category,
                    month=month,
                    amount=amount,
                    note="RPA 自动抓取（千牛财务报表）",
                )
            )
            session.log(f"抓到 {sub_category}（{month}）：¥{amount:.2f}")

    # ── 订单级卖家服务费 ────────────────────────────────────────
    if "order_fee_detail" in requested:
        session.open_workbench_page(
            rpa_config.qianniu_trade_url,
            QIANNIU["trade_menu_texts"],
            "trade",
            page_label="交易",
        )
        session.close_popups()
        # 订单明细页金额提取依赖页面表格结构，此处采用通用兜底；
        # 若页面改版导致取不到值，给出明确告警而不是静默写入 0。
        amount = session.extract_page_amount(hint_text="卖家服务费")
        if amount is None:
            result.warnings.append(
                "未能从千牛交易页面提取「卖家服务费」，可能页面已改版，"
                "请检查 rpa/selectors.py 或手动录入。"
            )
            session.screenshot("qianniu-order-fee-missing")
        else:
            month = _page_month(session.page) or "unknown"
            result.records.append(
                ExpenseRecord(
                    category="platform_fee",
                    sub_category="卖家服务费",
                    month=month,
                    amount=amount,
                    note="RPA 自动抓取（千牛交易页）",
                )
            )

    return result


def _safe_body_text(page) -> str:
    """读取页面全文；SPA 渲染慢，读为空就等待重试。"""
    for attempt in range(3):
        try:
            text = page.inner_text("body", timeout=5000)
        except Exception:  # noqa: BLE001
            text = ""
        if text.strip():
            return text
        if attempt < 2:
            time.sleep(2.0)
    return ""


def _extract_keyword_amount(session: BrowserSession, body_text: str, keyword: str) -> float | None:
    """在页面文本中定位关键词所在行并提取该行的金额。"""
    if keyword not in body_text:
        return None
    for line in body_text.splitlines():
        if keyword in line:
            amount = session.parse_amount(line)
            if amount is not None:
                return amount
    # 关键词单独一行，金额在下一行
    try:
        el = session.page.locator(f"text={keyword}").first
        sibling = el.locator("xpath=following-sibling::*[1]").first
        return session.parse_amount(sibling.inner_text(timeout=3000))
    except Exception:  # noqa: BLE001
        return None
