from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Optional

import openpyxl
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import text
from sqlmodel import Session, select

from database import get_session
from models import PLATFORMS, PlatformAccount, RPATask, StorePlatformExpense
from schemas import (
    BillImportItem,
    BillImportResult,
    DataSourceStatus,
    ExpenseAnalysisItem,
    ExpenseAnalysisKPI,
    ExpenseAnalysisResponse,
    ExpenseInput,
    ExpenseListResponse,
    ExpenseMonthlyItem,
    ExpenseRead,
    ExpenseUpdate,
    PureProfitKPI,
    PureProfitMonthItem,
    PureProfitResponse,
)

router = APIRouter(prefix="/profit", tags=["profit"])

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

_PO_EXCLUDED = ("等待买家付款", "退款中", "交易关闭")
_PO_EXCLUDED_SQL = ", ".join(f"'{s}'" for s in _PO_EXCLUDED)

# 需要从 StorePlatformExpense 拆出的费用类别 → KPI 字段后缀
_EXPENSE_FIELDS = {
    "platform_fee": "platform_fee",
    "promotion": "promotion",
    "shipping_insurance": "shipping_insurance",
    "other": "other",
}

_PLATFORM_LABELS = {"qianniu": "千牛工作台", "alimama": "阿里妈妈投放后台"}

# ── 汇总账单导入 ────────────────────────────────────────────────
MAX_BILL_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# 表头别名（比较前会去掉空白、统一全角括号）
_BILL_COLUMN_ALIASES = {
    "月份": "month",
    "业务大类": "business_type",
    "账单编号": "bill_no",
    "开票方向": "direction",
    "币种": "currency",
    "本月付款": "paid",
    "扣费金额合计(元)": "fee_total",
    "扣费金额合计": "fee_total",
    "本月交易额": "transaction_amount",
    "退款金额": "refund_amount",
}

_SKIP_BUSINESS_TYPES = {"合计", "总计", "小计", "汇总"}

_PROMOTION_KEYS = ("推广", "直通车", "万相台", "引力魔方", "超级推荐", "淘宝客")
_INSURANCE_KEYS = ("运费险", "订单险")
_PLATFORM_FEE_KEYS = ("服务费", "软件服务", "技术服务", "佣金", "扣费", "基础费", "增值费")


def _validate_month(value: Optional[str], param: str) -> None:
    if value is not None and not _MONTH_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail=f"参数 {param} 格式错误，应为 YYYY-MM，收到：{value}",
        )


def _norm_header(value) -> str:
    text_value = str(value or "")
    text_value = re.sub(r"[\s\u3000]+", "", text_value)
    return text_value.replace("（", "(").replace("）", ")")


def _to_amount(value) -> Optional[float]:
    """账单金额转 float；兼容千分位、货币符号和「暂无数据」。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace(",", "").replace("，", "")
    raw = raw.replace("¥", "").replace("￥", "")
    if not raw or raw in {"-", "--"} or "暂无" in raw:
        return None
    match = re.match(r"-?\d+(?:\.\d+)?", raw)
    return float(match.group()) if match else None


def _to_period_month(value) -> Optional[str]:
    """账单月份 → YYYY-MM；支持 202610 / 2026-10 / 2026/10 / Excel 日期。"""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m")
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) < 6:
        return None
    year, month = int(digits[:4]), int(digits[4:6])
    if 2000 <= year <= 2100 and 1 <= month <= 12:
        return f"{year:04d}-{month:02d}"
    return None


def _map_expense_category(business_type: str) -> str:
    text_value = business_type or ""
    if any(key in text_value for key in _PROMOTION_KEYS):
        return "promotion"
    if any(key in text_value for key in _INSURANCE_KEYS):
        return "shipping_insurance"
    if any(key in text_value for key in _PLATFORM_FEE_KEYS):
        return "platform_fee"
    return "other"


def _find_bill_header(rows: list[tuple]) -> tuple[Optional[int], dict[str, int]]:
    """在前 30 行里找表头，跳过标题/说明行。"""
    for row_index, row in enumerate(rows[:30]):
        mapping: dict[str, int] = {}
        for col_index, cell in enumerate(row):
            key = _BILL_COLUMN_ALIASES.get(_norm_header(cell))
            if key and key not in mapping:
                mapping[key] = col_index
        if (
            "month" in mapping
            and "business_type" in mapping
            and ("paid" in mapping or "fee_total" in mapping)
        ):
            return row_index, mapping
    return None, {}


def _cell(row: tuple, index: Optional[int]):
    if index is None or index >= len(row):
        return None
    return row[index]


# ---------------------------------------------------------------------------
# GET /api/profit/pure
# ---------------------------------------------------------------------------

@router.get("/pure", response_model=PureProfitResponse)
def pure_profit(
    start_month: Optional[str] = Query(default=None),
    end_month: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
) -> PureProfitResponse:
    """纯利润分析：收入 − 退款 − 采购成本 − 平台扣费 − 推广费 − 运费险 − 其它。"""
    _validate_month(start_month, "start_month")
    _validate_month(end_month, "end_month")

    # ── 收入 / 退款（SubOrder，口径与 009 首页一致） ─────────────
    so_where = ["COALESCE(paid_at, created_at) IS NOT NULL"]
    so_params: dict = {}
    if start_month:
        so_where.append("strftime('%Y-%m', COALESCE(paid_at, created_at)) >= :sm")
        so_params["sm"] = start_month
    if end_month:
        so_where.append("strftime('%Y-%m', COALESCE(paid_at, created_at)) <= :em")
        so_params["em"] = end_month

    so_sql = text(f"""
        SELECT
            store,
            strftime('%Y-%m', COALESCE(paid_at, created_at)) AS month_key,
            COALESCE(SUM(buyer_paid), 0)                  AS revenue,
            COALESCE(SUM(CAST(refund_amount AS REAL)), 0) AS refund
        FROM suborder
        WHERE {' AND '.join(so_where)}
        GROUP BY store, strftime('%Y-%m', COALESCE(paid_at, created_at))
        ORDER BY month_key
    """)
    so_rows = session.execute(so_sql, so_params).fetchall()

    # ── 采购成本（PurchaseOrder，排除未成交状态） ────────────────
    po_where = [
        "COALESCE(paid_at, created_at) IS NOT NULL",
        f"status NOT IN ({_PO_EXCLUDED_SQL})",
    ]
    po_params: dict = {}
    if start_month:
        po_where.append("strftime('%Y-%m', COALESCE(paid_at, created_at)) >= :sm")
        po_params["sm"] = start_month
    if end_month:
        po_where.append("strftime('%Y-%m', COALESCE(paid_at, created_at)) <= :em")
        po_params["em"] = end_month

    po_sql = text(f"""
        SELECT
            store,
            strftime('%Y-%m', COALESCE(paid_at, created_at)) AS month_key,
            COALESCE(SUM(paid_amount), 0) AS cost
        FROM purchaseorder
        WHERE {' AND '.join(po_where)}
        GROUP BY store, strftime('%Y-%m', COALESCE(paid_at, created_at))
        ORDER BY month_key
    """)
    po_rows = session.execute(po_sql, po_params).fetchall()

    # ── 额外费用（StorePlatformExpense，按类别 × 店铺 × 月聚合） ──
    exp_where = ["1=1"]
    exp_params: dict = {}
    if start_month:
        exp_where.append("period_month >= :sm")
        exp_params["sm"] = start_month
    if end_month:
        exp_where.append("period_month <= :em")
        exp_params["em"] = end_month

    exp_sql = text(f"""
        SELECT store, period_month, category, COALESCE(SUM(amount), 0) AS total
        FROM storeplatformexpense
        WHERE {' AND '.join(exp_where)}
        GROUP BY store, period_month, category
    """)
    exp_rows = session.execute(exp_sql, exp_params).fetchall()

    # ── 合并 ───────────────────────────────────────────────────
    buckets: dict[tuple[int, str], dict] = {}

    def _bucket(store: int, month: str) -> dict:
        return buckets.setdefault((store, month), {})

    for r in so_rows:
        _bucket(int(r.store), str(r.month_key)).update(
            revenue=float(r.revenue or 0.0), refund=float(r.refund or 0.0)
        )
    for r in po_rows:
        _bucket(int(r.store), str(r.month_key))["cost"] = float(r.cost or 0.0)
    for r in exp_rows:
        field = _EXPENSE_FIELDS.get(str(r.category))
        if field:
            _bucket(int(r.store), str(r.period_month))[field] = float(r.total or 0.0)

    all_months = sorted({mk for (_, mk) in buckets})
    if not all_months:
        return PureProfitResponse(
            months=[],
            items=[],
            kpi=_zero_kpi(),
            data_sources=_data_sources(session),
        )

    def _v(store: int, month: str, field: str) -> float:
        return buckets.get((store, month), {}).get(field, 0.0)

    items: list[PureProfitMonthItem] = []
    for month in all_months:
        item = PureProfitMonthItem(month=month)
        for store, suffix in ((1, "s1"), (2, "s2")):
            revenue = round(_v(store, month, "revenue"), 2)
            refund = round(_v(store, month, "refund"), 2)
            cost = round(_v(store, month, "cost"), 2)
            platform_fee = round(_v(store, month, "platform_fee"), 2)
            promotion = round(_v(store, month, "promotion"), 2)
            insurance = round(_v(store, month, "shipping_insurance"), 2)
            other = round(_v(store, month, "other"), 2)
            profit = round(
                revenue - refund - cost - platform_fee - promotion - insurance - other, 2
            )
            for name, value in (
                (f"revenue_{suffix}", revenue),
                (f"refund_{suffix}", refund),
                (f"cost_{suffix}", cost),
                (f"platform_fee_{suffix}", platform_fee),
                (f"promotion_{suffix}", promotion),
                (f"shipping_insurance_{suffix}", insurance),
                (f"other_{suffix}", other),
                (f"profit_{suffix}", profit),
            ):
                setattr(item, name, value)
        items.append(item)

    kpi = _build_kpi(items)
    return PureProfitResponse(
        months=all_months,
        items=items,
        kpi=kpi,
        data_sources=_data_sources(session),
    )


# ---------------------------------------------------------------------------
# GET /api/profit/expense-analysis
# ---------------------------------------------------------------------------

_EXPENSE_CATEGORIES = ("platform_fee", "promotion", "shipping_insurance", "other")


def _roi(transaction_amount: float, expense: float) -> Optional[float]:
    """ROI = 交易额 / 费用；缺交易额或费用时返回 None（前端显示为空点）。"""
    if expense <= 0 or transaction_amount <= 0:
        return None
    return round(transaction_amount / expense, 2)


def _month_sequence(start: str, end: str) -> list[str]:
    year, month = int(start[:4]), int(start[5:7])
    end_year, end_month = int(end[:4]), int(end[5:7])
    months: list[str] = []
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


@router.get("/expense-analysis", response_model=ExpenseAnalysisResponse)
def get_expense_analysis(
    start_month: Optional[str] = Query(default=None),
    end_month: Optional[str] = Query(default=None),
    store: Optional[int] = Query(default=None, ge=1, le=2),
    session: Session = Depends(get_session),
) -> ExpenseAnalysisResponse:
    """运营费用分析：按月分类走势 + 各费用项（业务大类）汇总。"""
    _validate_month(start_month, "start_month")
    _validate_month(end_month, "end_month")
    if start_month and end_month and start_month > end_month:
        raise HTTPException(status_code=422, detail="start_month 不能晚于 end_month")

    stmt = select(StorePlatformExpense)
    if start_month:
        stmt = stmt.where(StorePlatformExpense.period_month >= start_month)
    if end_month:
        stmt = stmt.where(StorePlatformExpense.period_month <= end_month)
    if store is not None:
        stmt = stmt.where(StorePlatformExpense.store == store)
    rows = session.exec(stmt).all()

    data_months = sorted(
        {r.period_month for r in rows if r.period_month and _MONTH_RE.match(r.period_month)}
    )
    if not data_months:
        return ExpenseAnalysisResponse()

    if start_month and end_month:
        months = _month_sequence(start_month, end_month)
    elif start_month:
        months = _month_sequence(start_month, data_months[-1])
    elif end_month:
        months = _month_sequence(data_months[0], end_month)
    else:
        months = _month_sequence(data_months[0], data_months[-1])
    if len(months) > 120:
        raise HTTPException(status_code=422, detail="时间范围过大，最多支持 120 个月")

    monthly_map: dict[str, dict[str, float]] = {
        month: dict.fromkeys(_EXPENSE_CATEGORIES, 0.0) for month in months
    }
    # 交易额按「月份」「月份 × 费用项」分别累加，用于计算 ROI
    monthly_transaction: dict[str, float] = dict.fromkeys(months, 0.0)
    item_map: dict[tuple[str, str], dict[str, float]] = {}
    item_transaction: dict[tuple[str, str], float] = {}

    for row in rows:
        bucket = monthly_map.get(row.period_month)
        if bucket is None:
            continue
        category = row.category if row.category in _EXPENSE_CATEGORIES else "other"
        amount = float(row.amount or 0.0)
        bucket[category] += amount

        name = (row.sub_category or "").strip() or "未分类"
        key = (category, name)
        item_monthly = item_map.setdefault(key, dict.fromkeys(months, 0.0))
        item_monthly[row.period_month] += amount

        transaction_amount = float(row.transaction_amount or 0.0)
        monthly_transaction[row.period_month] += transaction_amount
        item_transaction[key] = item_transaction.get(key, 0.0) + transaction_amount

    monthly_items: list[ExpenseMonthlyItem] = []
    month_totals: dict[str, float] = {}
    category_totals: dict[str, float] = dict.fromkeys(_EXPENSE_CATEGORIES, 0.0)
    for month in months:
        values = monthly_map[month]
        for category, amount in values.items():
            category_totals[category] += amount
        total = round(sum(values.values()), 2)
        month_totals[month] = total
        transaction_amount = round(monthly_transaction[month], 2)
        monthly_items.append(
            ExpenseMonthlyItem(
                month=month,
                platform_fee=round(values["platform_fee"], 2),
                promotion=round(values["promotion"], 2),
                shipping_insurance=round(values["shipping_insurance"], 2),
                other=round(values["other"], 2),
                total=total,
                transaction_amount=transaction_amount,
                roi=_roi(transaction_amount, total),
            )
        )

    grand_total = round(sum(month_totals.values()), 2)
    data_month_count = sum(1 for total in month_totals.values() if total > 0)
    latest_month = next(
        (month for month in reversed(months) if month_totals[month] > 0), None
    )
    prev_month = None
    if latest_month is not None:
        latest_index = months.index(latest_month)
        if latest_index > 0:
            prev_month = months[latest_index - 1]

    items: list[ExpenseAnalysisItem] = []
    for (category, name), values in item_map.items():
        item_total = round(sum(values.values()), 2)
        latest_amount = round(values.get(latest_month, 0.0), 2) if latest_month else 0.0
        mom_pct = None
        if latest_month and prev_month:
            previous_amount = values.get(prev_month, 0.0)
            if previous_amount > 0:
                mom_pct = round(
                    (latest_amount - previous_amount) / previous_amount * 100, 2
                )
        item_transaction_total = round(item_transaction.get((category, name), 0.0), 2)
        items.append(
            ExpenseAnalysisItem(
                name=name,
                category=category,
                total=item_total,
                share_pct=round(item_total / grand_total * 100, 2) if grand_total else 0.0,
                latest_amount=latest_amount,
                mom_pct=mom_pct,
                transaction_amount=item_transaction_total,
                roi=_roi(item_transaction_total, item_total),
                monthly={month: round(amount, 2) for month, amount in values.items()},
            )
        )
    items.sort(key=lambda item: -item.total)

    top_category = max(category_totals, key=category_totals.get) if grand_total else None
    mom_pct = None
    if latest_month and prev_month and month_totals[prev_month] > 0:
        mom_pct = round(
            (month_totals[latest_month] - month_totals[prev_month])
            / month_totals[prev_month]
            * 100,
            2,
        )

    total_transaction_amount = round(sum(monthly_transaction.values()), 2)
    latest_transaction_amount = (
        round(monthly_transaction[latest_month], 2) if latest_month else 0.0
    )

    kpi = ExpenseAnalysisKPI(
        total_expense=grand_total,
        avg_monthly=round(grand_total / data_month_count, 2) if data_month_count else 0.0,
        month_count=data_month_count,
        latest_month=latest_month,
        mom_pct=mom_pct,
        total_transaction_amount=total_transaction_amount,
        roi=_roi(total_transaction_amount, grand_total),
        latest_roi=_roi(latest_transaction_amount, month_totals.get(latest_month, 0.0))
        if latest_month
        else None,
        top_category=top_category,
        top_category_amount=round(category_totals[top_category], 2) if top_category else 0.0,
        top_item=items[0].name if items else None,
        top_item_amount=items[0].total if items else 0.0,
    )
    return ExpenseAnalysisResponse(
        months=months,
        monthly=monthly_items,
        items=items,
        kpi=kpi,
    )


# ---------------------------------------------------------------------------
# 额外费用 CRUD（手动录入 / 修正 RPA 抓取结果）
# ---------------------------------------------------------------------------

@router.get("/expenses", response_model=ExpenseListResponse)
def list_expenses(
    start_month: Optional[str] = Query(default=None),
    end_month: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    store: Optional[int] = Query(default=None, ge=1, le=2),
    source: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
) -> ExpenseListResponse:
    _validate_month(start_month, "start_month")
    _validate_month(end_month, "end_month")

    stmt = select(StorePlatformExpense)
    if start_month:
        stmt = stmt.where(StorePlatformExpense.period_month >= start_month)
    if end_month:
        stmt = stmt.where(StorePlatformExpense.period_month <= end_month)
    if category:
        stmt = stmt.where(StorePlatformExpense.category == category)
    if store is not None:
        stmt = stmt.where(StorePlatformExpense.store == store)
    if source:
        stmt = stmt.where(StorePlatformExpense.source == source)
    stmt = stmt.order_by(StorePlatformExpense.period_month)  # type: ignore[attr-defined]

    rows = session.exec(stmt).all()
    return ExpenseListResponse(
        total=len(rows),
        items=[
            ExpenseRead(
                id=r.id or 0,
                store=r.store,
                period_month=r.period_month,
                category=r.category,
                sub_category=r.sub_category,
                amount=r.amount,
                source=r.source,
                rpa_task_id=r.rpa_task_id,
                note=r.note,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


@router.post("/expenses/import-bill", response_model=BillImportResult)
async def import_expense_bill(
    file: UploadFile = File(...),
    store: int = Form(...),
    session: Session = Depends(get_session),
) -> BillImportResult:
    """导入淘宝「汇总账单.xlsx」，写入 StorePlatformExpense（source=xlsx）。

    按「月份 × 业务大类」覆盖同一条记录，金额取「本月付款」；
    业务大类自动归入 平台扣费 / 推广费 / 运费险 / 其它费用。
    """
    if store not in (1, 2):
        raise HTTPException(status_code=422, detail="store 必须为 1 或 2")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="文件内容为空")
    if len(content) > MAX_BILL_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件过大，请检查")

    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 .xlsx / .xlsm 格式的汇总账单",
        )

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无法解析文件，请确认为有效的 Excel 文件",
        )

    # 优先在名字含「账单」的 sheet 里找表头，找不到再试其它 sheet
    header_index: Optional[int] = None
    col_map: dict[str, int] = {}
    rows: list[tuple] = []
    sheets = sorted(
        workbook.worksheets,
        key=lambda sheet: 0 if "账单" in sheet.title else 1,
    )
    for sheet in sheets:
        sheet_rows = list(sheet.iter_rows(values_only=True))
        index, mapping = _find_bill_header(sheet_rows)
        if index is not None:
            rows, header_index, col_map = sheet_rows, index, mapping
            break

    if header_index is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="未找到账单表头，需要包含：月份、业务大类、本月付款（或扣费金额合计）",
        )

    idx_month = col_map["month"]
    idx_business = col_map["business_type"]
    idx_paid = col_map.get("paid")
    idx_fee_total = col_map.get("fee_total")
    idx_bill_no = col_map.get("bill_no")
    idx_transaction = col_map.get("transaction_amount")

    imported = 0
    updated = 0
    errors: list[str] = []
    items: list[BillImportItem] = []
    months: set[str] = set()
    total_amount = 0.0

    # 同一个月 + 业务大类可能出现多张账单，先按库表唯一键汇总，避免后者覆盖前者
    aggregated: dict[tuple[str, str], dict] = {}

    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        business_type = str(_cell(row, idx_business) or "").strip()
        if not business_type or business_type in _SKIP_BUSINESS_TYPES:
            continue

        period_month = _to_period_month(_cell(row, idx_month))
        if period_month is None:
            errors.append(f"第 {offset} 行：月份无法识别")
            continue

        amount = _to_amount(_cell(row, idx_paid))
        if amount is None:
            amount = _to_amount(_cell(row, idx_fee_total))
        if amount is None:
            errors.append(f"第 {offset} 行（{business_type}）：金额无法识别")
            continue

        note_parts = []
        bill_no = _cell(row, idx_bill_no)
        if bill_no not in (None, ""):
            note_parts.append(f"账单 {str(bill_no).strip()}")
        transaction_amount = _to_amount(_cell(row, idx_transaction))

        key = (period_month, business_type[:200])
        entry = aggregated.setdefault(
            key,
            {
                "business_type": business_type,
                "category": _map_expense_category(business_type),
                "amount": 0.0,
                "transaction_amount": 0.0,
                "notes": [],
            },
        )
        entry["amount"] += amount
        if transaction_amount is not None:
            # 交易额用于计算 ROI，按「月份 × 业务大类」累加
            entry["transaction_amount"] += transaction_amount
        if note_parts:
            entry["notes"].append("；".join(note_parts))

    for (period_month, sub_category), entry in aggregated.items():
        amount = entry["amount"]
        transaction_amount = round(entry["transaction_amount"], 2)
        business_type = entry["business_type"]
        category = entry["category"]
        note = "；".join(entry["notes"])[:500] or None

        existing = session.exec(
            select(StorePlatformExpense).where(
                StorePlatformExpense.store == store,
                StorePlatformExpense.period_month == period_month,
                StorePlatformExpense.category == category,
                StorePlatformExpense.sub_category == sub_category,
            )
        ).first()

        if existing is not None:
            existing.amount = amount
            existing.transaction_amount = transaction_amount
            existing.source = "xlsx"
            existing.note = note
            session.add(existing)
            action = "updated"
            updated += 1
        else:
            session.add(
                StorePlatformExpense(
                    store=store,
                    period_month=period_month,
                    category=category,
                    sub_category=sub_category,
                    amount=amount,
                    transaction_amount=transaction_amount,
                    source="xlsx",
                    note=note,
                )
            )
            action = "imported"
            imported += 1

        months.add(period_month)
        total_amount += amount
        items.append(
            BillImportItem(
                period_month=period_month,
                business_type=business_type,
                category=category,
                amount=round(amount, 2),
                transaction_amount=transaction_amount,
                action=action,
            )
        )

    session.commit()

    if not items and not errors:
        raise HTTPException(status_code=422, detail="账单中没有可导入的数据行")

    return BillImportResult(
        imported=imported,
        updated=updated,
        errors=errors,
        items=items,
        month="、".join(sorted(months)) or None,
        total_amount=round(total_amount, 2),
    )


@router.post("/expenses", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(payload: ExpenseInput, session: Session = Depends(get_session)) -> ExpenseRead:
    sub = payload.sub_category or ""
    existing = session.exec(
        select(StorePlatformExpense).where(
            StorePlatformExpense.store == payload.store,
            StorePlatformExpense.period_month == payload.period_month,
            StorePlatformExpense.category == payload.category,
            StorePlatformExpense.sub_category == sub,
        )
    ).first()
    if existing is not None:
        existing.amount = payload.amount
        existing.transaction_amount = payload.transaction_amount
        existing.note = payload.note
        existing.source = "manual"
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return _to_expense_read(existing)

    record = StorePlatformExpense(
        store=payload.store,
        period_month=payload.period_month,
        category=payload.category,
        sub_category=sub,
        amount=payload.amount,
        transaction_amount=payload.transaction_amount,
        source="manual",
        note=payload.note,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return _to_expense_read(record)


@router.put("/expenses/{expense_id}", response_model=ExpenseRead)
def update_expense(
    expense_id: int, payload: ExpenseUpdate, session: Session = Depends(get_session)
) -> ExpenseRead:
    record = session.get(StorePlatformExpense, expense_id)
    if record is None:
        raise HTTPException(status_code=404, detail="费用记录不存在")
    if payload.amount is not None:
        record.amount = payload.amount
    if payload.transaction_amount is not None:
        record.transaction_amount = payload.transaction_amount
    if payload.note is not None:
        record.note = payload.note
    session.add(record)
    session.commit()
    session.refresh(record)
    return _to_expense_read(record)


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: int, session: Session = Depends(get_session)) -> None:
    record = session.get(StorePlatformExpense, expense_id)
    if record is None:
        raise HTTPException(status_code=404, detail="费用记录不存在")
    session.delete(record)
    session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_expense_read(record: StorePlatformExpense) -> ExpenseRead:
    return ExpenseRead(
        id=record.id or 0,
        store=record.store,
        period_month=record.period_month,
        category=record.category,
        sub_category=record.sub_category,
        amount=record.amount,
        transaction_amount=record.transaction_amount or 0.0,
        source=record.source,
        rpa_task_id=record.rpa_task_id,
        note=record.note,
        created_at=record.created_at,
    )


def _zero_kpi() -> PureProfitKPI:
    return PureProfitKPI(**{f: 0.0 for f in PureProfitKPI.model_fields})


def _build_kpi(items: list[PureProfitMonthItem]) -> PureProfitKPI:
    def _sum(field: str) -> float:
        return round(sum(getattr(item, field) for item in items), 2)

    kpi = PureProfitKPI(
        revenue_s1=_sum("revenue_s1"), revenue_s2=_sum("revenue_s2"),
        refund_s1=_sum("refund_s1"), refund_s2=_sum("refund_s2"),
        cost_s1=_sum("cost_s1"), cost_s2=_sum("cost_s2"),
        platform_fee_s1=_sum("platform_fee_s1"), platform_fee_s2=_sum("platform_fee_s2"),
        promotion_s1=_sum("promotion_s1"), promotion_s2=_sum("promotion_s2"),
        shipping_insurance_s1=_sum("shipping_insurance_s1"),
        shipping_insurance_s2=_sum("shipping_insurance_s2"),
        other_s1=_sum("other_s1"), other_s2=_sum("other_s2"),
        profit_s1=_sum("profit_s1"), profit_s2=_sum("profit_s2"),
        total_revenue=round(_sum("revenue_s1") + _sum("revenue_s2"), 2),
        total_refund=round(_sum("refund_s1") + _sum("refund_s2"), 2),
        total_cost=round(_sum("cost_s1") + _sum("cost_s2"), 2),
        total_platform_fee=round(_sum("platform_fee_s1") + _sum("platform_fee_s2"), 2),
        total_promotion=round(_sum("promotion_s1") + _sum("promotion_s2"), 2),
        total_shipping_insurance=round(
            _sum("shipping_insurance_s1") + _sum("shipping_insurance_s2"), 2
        ),
        total_other=round(_sum("other_s1") + _sum("other_s2"), 2),
        total_profit=round(_sum("profit_s1") + _sum("profit_s2"), 2),
    )

    net_revenue = round(kpi.total_revenue - kpi.total_refund, 2)
    if net_revenue > 0:
        kpi.total_profit_margin_pct = round(kpi.total_profit / net_revenue * 100, 2)

    # ── 环比：最近一个完整月 vs 上一月 ───────────────────────────
    if len(items) >= 2:
        latest, previous = items[-1], items[-2]
        latest_profit = round(latest.profit_s1 + latest.profit_s2, 2)
        prev_profit = round(previous.profit_s1 + previous.profit_s2, 2)
        latest_net = round(latest.revenue_s1 + latest.revenue_s2
                           - latest.refund_s1 - latest.refund_s2, 2)
        prev_net = round(previous.revenue_s1 + previous.revenue_s2
                         - previous.refund_s1 - previous.refund_s2, 2)

        kpi.latest_month = latest.month
        if prev_profit != 0:
            kpi.profit_mom_pct = round((latest_profit - prev_profit) / abs(prev_profit) * 100, 2)
        if latest_net > 0:
            latest_margin = round(latest_profit / latest_net * 100, 2)
            if prev_net > 0:
                kpi.margin_mom_pct = round(
                    latest_margin - round(prev_profit / prev_net * 100, 2), 2
                )
    return kpi


def _data_sources(session: Session) -> list[DataSourceStatus]:
    """各 RPA 平台最近一次抓取状态 + 已配置账号数。"""
    statuses: list[DataSourceStatus] = []
    for platform in PLATFORMS:
        accounts = session.exec(
            select(PlatformAccount).where(PlatformAccount.platform == platform)
        ).all()
        last_task = session.exec(
            select(RPATask)
            .where(RPATask.platform == platform)
            .order_by(RPATask.id.desc())  # type: ignore[attr-defined]
        ).first()
        statuses.append(
            DataSourceStatus(
                platform=platform,
                label=_PLATFORM_LABELS.get(platform, platform),
                last_task_status=last_task.status if last_task else None,
                last_finished_at=last_task.finished_at if last_task else None,
                account_count=len(accounts),
                configured=len(accounts) > 0,
            )
        )
    return statuses
