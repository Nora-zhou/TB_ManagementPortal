from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlmodel import Session

from database import get_session
from schemas import ProfitMonthlyKPI, ProfitMonthlySeries, ProfitMonthlyResponse

router = APIRouter(prefix="/stats", tags=["stats"])

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

_PO_EXCLUDED = ("等待买家付款", "退款中", "交易关闭")

# Pre-built SQL fragment for PO excluded statuses
_PO_EXCLUDED_SQL = ", ".join(f"'{s}'" for s in _PO_EXCLUDED)


def _validate_month(value: Optional[str], param: str) -> None:
    if value is not None and not _MONTH_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail=f"参数 {param} 格式错误，应为 YYYY-MM，收到：{value}",
        )


_ZERO_KPI = ProfitMonthlyKPI(
    revenue_s1=0.0, revenue_s2=0.0, cost_s1=0.0, cost_s2=0.0,
    refund_s1=0.0, refund_s2=0.0, profit_s1=0.0, profit_s2=0.0,
    total_revenue=0.0, total_cost=0.0, total_refund=0.0, total_profit=0.0,
)
_EMPTY_SERIES = ProfitMonthlySeries(
    revenue_s1=[], revenue_s2=[], cost_s1=[], cost_s2=[],
    refund_s1=[], refund_s2=[], profit_s1=[], profit_s2=[],
    total_revenue=[], total_cost=[], total_refund=[], total_profit=[],
)


# ---------------------------------------------------------------------------
# GET /api/stats/profit-monthly
# ---------------------------------------------------------------------------

@router.get("/profit-monthly", response_model=ProfitMonthlyResponse)
def profit_monthly(
    start_month: Optional[str] = Query(default=None),
    end_month: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
) -> ProfitMonthlyResponse:
    _validate_month(start_month, "start_month")
    _validate_month(end_month, "end_month")

    # ── SubOrder aggregation ──────────────────────────────────────────────
    so_where = ["COALESCE(paid_at, created_at) IS NOT NULL"]
    so_params: dict = {}
    if start_month:
        so_where.append("strftime('%Y-%m', COALESCE(paid_at, created_at)) >= :sm")
        so_params["sm"] = start_month
    if end_month:
        so_where.append("strftime('%Y-%m', COALESCE(paid_at, created_at)) <= :em")
        so_params["em"] = end_month

    # Revenue and refund: SUM all rows regardless of status, matching the
    # formula used by GET /api/orders/stats/summary (the order-list dashboard).
    so_sql = text(f"""
        SELECT
            store,
            strftime('%Y-%m', COALESCE(paid_at, created_at)) AS month_key,
            COALESCE(SUM(buyer_paid), 0)                    AS revenue,
            COALESCE(SUM(CAST(refund_amount AS REAL)), 0)   AS refund
        FROM suborder
        WHERE {' AND '.join(so_where)}
        GROUP BY store, strftime('%Y-%m', COALESCE(paid_at, created_at))
        ORDER BY month_key
    """)
    so_rows = session.execute(so_sql, so_params).fetchall()

    # ── PurchaseOrder aggregation ─────────────────────────────────────────
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

    # ── Merge into keyed dict ─────────────────────────────────────────────
    data: dict[tuple[int, str], dict] = {}
    for r in so_rows:
        key = (int(r.store), str(r.month_key))
        bucket = data.setdefault(key, {})
        bucket["revenue"] = float(r.revenue or 0.0)
        bucket["refund"] = float(r.refund or 0.0)
    for r in po_rows:
        key = (int(r.store), str(r.month_key))
        bucket = data.setdefault(key, {})
        bucket["cost"] = float(r.cost or 0.0)

    all_months = sorted({mk for (_, mk) in data.keys()})
    if not all_months:
        return ProfitMonthlyResponse(months=[], series=_EMPTY_SERIES, kpi=_ZERO_KPI)

    # ── Build per-store monthly series ────────────────────────────────────
    def _v(store: int, month: str, field: str) -> float:
        return data.get((store, month), {}).get(field, 0.0)

    rev_s1    = [round(_v(1, m, "revenue"), 2) for m in all_months]
    rev_s2    = [round(_v(2, m, "revenue"), 2) for m in all_months]
    refund_s1 = [round(_v(1, m, "refund"),  2) for m in all_months]
    refund_s2 = [round(_v(2, m, "refund"),  2) for m in all_months]
    cost_s1   = [round(_v(1, m, "cost"),    2) for m in all_months]
    cost_s2   = [round(_v(2, m, "cost"),    2) for m in all_months]

    profit_s1 = [round(rev_s1[i] - refund_s1[i] - cost_s1[i], 2) for i in range(len(all_months))]
    profit_s2 = [round(rev_s2[i] - refund_s2[i] - cost_s2[i], 2) for i in range(len(all_months))]

    total_revenue = [round(rev_s1[i] + rev_s2[i], 2)             for i in range(len(all_months))]
    total_cost    = [round(cost_s1[i] + cost_s2[i], 2)           for i in range(len(all_months))]
    total_refund  = [round(refund_s1[i] + refund_s2[i], 2)       for i in range(len(all_months))]
    total_profit  = [round(profit_s1[i] + profit_s2[i], 2)       for i in range(len(all_months))]

    series = ProfitMonthlySeries(
        revenue_s1=rev_s1,     revenue_s2=rev_s2,
        cost_s1=cost_s1,       cost_s2=cost_s2,
        refund_s1=refund_s1,   refund_s2=refund_s2,
        profit_s1=profit_s1,   profit_s2=profit_s2,
        total_revenue=total_revenue, total_cost=total_cost,
        total_refund=total_refund,   total_profit=total_profit,
    )

    # ── KPI (period totals) ───────────────────────────────────────────────
    def _sum(lst: list[float]) -> float:
        return round(sum(lst), 2)

    kpi_profit_s1 = round(_sum(rev_s1) - _sum(refund_s1) - _sum(cost_s1), 2)
    kpi_profit_s2 = round(_sum(rev_s2) - _sum(refund_s2) - _sum(cost_s2), 2)

    kpi = ProfitMonthlyKPI(
        revenue_s1=_sum(rev_s1),
        revenue_s2=_sum(rev_s2),
        cost_s1=_sum(cost_s1),
        cost_s2=_sum(cost_s2),
        refund_s1=_sum(refund_s1),
        refund_s2=_sum(refund_s2),
        profit_s1=kpi_profit_s1,
        profit_s2=kpi_profit_s2,
        total_revenue=round(_sum(rev_s1) + _sum(rev_s2), 2),
        total_cost=round(_sum(cost_s1) + _sum(cost_s2), 2),
        total_refund=round(_sum(refund_s1) + _sum(refund_s2), 2),
        total_profit=round(kpi_profit_s1 + kpi_profit_s2, 2),
    )

    return ProfitMonthlyResponse(months=all_months, series=series, kpi=kpi)
