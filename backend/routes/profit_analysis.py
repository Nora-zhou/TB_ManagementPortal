from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlmodel import Session, select

from database import get_session
from models import PLATFORMS, PlatformAccount, RPATask, StorePlatformExpense
from schemas import (
    DataSourceStatus,
    ExpenseInput,
    ExpenseListResponse,
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


def _validate_month(value: Optional[str], param: str) -> None:
    if value is not None and not _MONTH_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail=f"参数 {param} 格式错误，应为 YYYY-MM，收到：{value}",
        )


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
# 额外费用 CRUD（手动录入 / 修正 RPA 抓取结果）
# ---------------------------------------------------------------------------

@router.get("/expenses", response_model=ExpenseListResponse)
def list_expenses(
    start_month: Optional[str] = Query(default=None),
    end_month: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
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
