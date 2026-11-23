"""导入后自动核对：库内订单月度汇总 × 生意参谋月度基准。

两条检查线：
1. 外部对账：把 suborder 汇总（销售额 / 退款 / 件数 / 单数）与手工登记的
   生意参谋月度指标比对，差异率超阈值即判定为「疑似漏单」。
2. 内部一致性：某月日均单量相对相邻月骤降（< 70%）时报警——即使没录入平台
   数据，也能在导入后立刻发现「这个月的单没导全」。
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Float as SAFloat
from sqlalchemy import cast as sa_cast
from sqlmodel import Session, func, select

from database import get_session
from models import PlatformMonthStat, SubOrder
from schemas import (
    MonthCheck,
    PlatformMonthStatRead,
    PlatformMonthStatUpsert,
    ReconcileResponse,
)

router = APIRouter(prefix="/reconcile", tags=["reconcile"])

# 差异率阈值（百分比）
DIFF_OK_PCT = 5.0      # 在此以内视为一致
DIFF_GAP_PCT = 15.0    # 超过则判定明显缺口
# 相邻月日均单量比值下限，低于则视为异常下降
NEIGHBOR_LOW_RATIO = 0.7

_MONTH_PATTERN = r"^\d{4}-\d{2}$"


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _month_bounds(month: str) -> tuple[datetime, datetime]:
    year, mon = int(month[:4]), int(month[5:7])
    start = datetime(year, mon, 1)
    end = datetime(year + 1, 1, 1) if mon == 12 else datetime(year, mon + 1, 1)
    return start, end


def _shift_month(month: str, delta: int) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _expected_days(month: str, today: Optional[date] = None) -> int:
    """该月已过去的天数（未来月份返回 0）。"""
    today = today or date.today()
    year, mon = int(month[:4]), int(month[5:7])
    total = calendar.monthrange(year, mon)[1]
    if (year, mon) > (today.year, today.month):
        return 0
    if (year, mon) == (today.year, today.month):
        return today.day
    return total


def month_aggregate(session: Session, month: str, store: Optional[int] = None) -> dict:
    """按月汇总 suborder。"""
    start, end = _month_bounds(month)
    stmt = (
        select(
            func.coalesce(func.sum(SubOrder.buyer_paid), 0.0),
            func.coalesce(func.sum(sa_cast(SubOrder.refund_amount, SAFloat)), 0.0),
            func.coalesce(func.sum(SubOrder.quantity), 0),
            func.count(func.distinct(SubOrder.main_order_id)),
            func.count(func.distinct(func.date(SubOrder.created_at))),
        )
        .select_from(SubOrder)
        .where(SubOrder.created_at >= start, SubOrder.created_at < end)
    )
    if store is not None:
        stmt = stmt.where(SubOrder.store == store)
    pay, refund, items, orders, days = session.exec(stmt).one()
    return {
        "pay": float(pay or 0.0),
        "refund": float(refund or 0.0),
        "items": int(items or 0),
        "orders": int(orders or 0),
        "days": int(days or 0),
    }


def _diff_pct(db_value: float, platform_value: Optional[float]) -> Optional[float]:
    if platform_value is None or platform_value == 0:
        return None
    return round((db_value / platform_value - 1) * 100, 1)


def _platform_stats(session: Session, store: Optional[int]) -> dict[str, PlatformMonthStat]:
    # 未指定店铺时不合并平台基准，避免与「全店汇总」错配
    if store is None:
        return {}
    rows = session.exec(
        select(PlatformMonthStat).where(PlatformMonthStat.store == store)
    ).all()
    return {row.period_month: row for row in rows}


def _neighbor_daily_avg(session: Session, month: str, store: Optional[int]) -> Optional[float]:
    """相邻两个月（有数据的）日均单量均值。"""
    others: list[float] = []
    for delta in (-1, 1):
        neighbor = _shift_month(month, delta)
        expected = _expected_days(neighbor)
        if expected <= 0:
            continue
        agg = month_aggregate(session, neighbor, store)
        if agg["orders"] > 0:
            others.append(agg["orders"] / expected)
    if not others:
        return None
    return sum(others) / len(others)


def build_month_check(
    session: Session,
    month: str,
    store: Optional[int],
    platform: Optional[PlatformMonthStat] = None,
) -> MonthCheck:
    agg = month_aggregate(session, month, store)
    expected_days = _expected_days(month)
    hints: list[str] = []

    has_platform = platform is not None
    pay_diff = items_diff = refund_diff = buyers_diff = None
    if has_platform:
        pay_diff = _diff_pct(agg["pay"], platform.pay_amount)
        refund_diff = _diff_pct(agg["refund"], platform.refund_amount)
        items_diff = _diff_pct(agg["items"], platform.paid_items)
        buyers_diff = _diff_pct(agg["orders"], platform.paid_buyers)

    # ── 外部对账提示 ──
    if not has_platform:
        hints.append("未录入该月生意参谋数据，本次仅做内部一致性检查")
    else:
        if pay_diff is not None and abs(pay_diff) > DIFF_OK_PCT:
            direction = "少" if pay_diff < 0 else "多"
            hints.append(
                f"销售额比平台{direction} {abs(pay_diff):.1f}%"
                f"（库内 ¥{agg['pay']:,.2f} / 平台 ¥{platform.pay_amount:,.2f}）"
            )
        if items_diff is not None and abs(items_diff) > DIFF_OK_PCT * 2:
            hints.append(f"支付件数差异 {items_diff:+.1f}%，多为多件订单子订单缺行")
        if refund_diff is not None and abs(refund_diff) > DIFF_GAP_PCT:
            hints.append(f"退款金额差异 {refund_diff:+.1f}%")

    # ── 内部一致性提示 ──
    if agg["orders"] == 0:
        hints.append("该月库内没有订单数据")
    else:
        if expected_days and agg["days"] < expected_days:
            hints.append(f"有单天数 {agg['days']}/{expected_days} 天")
        neighbor_avg = _neighbor_daily_avg(session, month, store)
        if neighbor_avg:
            daily = agg["orders"] / expected_days if expected_days else 0
            ratio = daily / neighbor_avg
            if ratio < NEIGHBOR_LOW_RATIO:
                hints.append(
                    f"日均单量仅为相邻月的 {ratio * 100:.0f}%"
                    f"（{daily:.1f} vs {neighbor_avg:.1f} 单/天），疑似漏单"
                )
            elif ratio > 1 / NEIGHBOR_LOW_RATIO:
                hints.append(f"日均单量为相邻月的 {ratio * 100:.0f}%，明显放量，请确认口径")

    # ── 结论 ──
    if agg["orders"] == 0:
        status = "gap"
    elif has_platform:
        worst = max(
            (abs(v) for v in (pay_diff, refund_diff, items_diff) if v is not None),
            default=0.0,
        )
        status = "gap" if worst > DIFF_GAP_PCT else "warning" if worst > DIFF_OK_PCT else "ok"
    else:
        status = "warning" if any("疑似漏单" in h for h in hints) else "ok"

    return MonthCheck(
        month=month,
        store=store,
        db_pay_amount=round(agg["pay"], 2),
        db_refund_amount=round(agg["refund"], 2),
        db_items=agg["items"],
        db_orders=agg["orders"],
        days_with_data=agg["days"],
        expected_days=expected_days,
        platform_pay_amount=platform.pay_amount if platform else None,
        platform_refund_amount=platform.refund_amount if platform else None,
        platform_paid_items=platform.paid_items if platform else None,
        platform_paid_buyers=platform.paid_buyers if platform else None,
        pay_diff_pct=pay_diff,
        refund_diff_pct=refund_diff,
        items_diff_pct=items_diff,
        buyers_diff_pct=buyers_diff,
        has_platform=has_platform,
        status=status,
        hints=hints,
    )


def check_months(session: Session, months: list[str], store: Optional[int] = None) -> list[MonthCheck]:
    """供导入接口复用的入口：给定月份列表，返回核对结果。"""
    platform_map = _platform_stats(session, store)
    return [build_month_check(session, m, store, platform_map.get(m)) for m in sorted(set(months))]


# ---------------------------------------------------------------------------
# GET /api/reconcile/monthly
# ---------------------------------------------------------------------------

@router.get("/monthly", response_model=ReconcileResponse)
def reconcile_monthly(
    session: Session = Depends(get_session),
    store: Optional[int] = Query(default=1),
    start_month: Optional[str] = Query(default=None, pattern=_MONTH_PATTERN),
    end_month: Optional[str] = Query(default=None, pattern=_MONTH_PATTERN),
):
    if start_month is None or end_month is None:
        min_row = session.exec(select(func.min(SubOrder.created_at))).one()
        max_row = session.exec(select(func.max(SubOrder.created_at))).one()
        if min_row is None or max_row is None:
            return ReconcileResponse(store=store, items=[], checked_at=datetime.now(timezone.utc))
        start_month = start_month or str(min_row)[:7]
        end_month = end_month or str(max_row)[:7]

    months: list[str] = []
    cursor = start_month
    for _ in range(240):  # 最多 20 年，防死循环
        months.append(cursor)
        if cursor >= end_month:
            break
        cursor = _shift_month(cursor, 1)

    return ReconcileResponse(
        store=store,
        items=check_months(session, months, store),
        checked_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# 平台月度基准：读写
# ---------------------------------------------------------------------------

@router.get("/platform-stats", response_model=list[PlatformMonthStatRead])
def list_platform_stats(
    session: Session = Depends(get_session),
    store: Optional[int] = Query(default=None),
):
    stmt = select(PlatformMonthStat).order_by(
        PlatformMonthStat.store, PlatformMonthStat.period_month
    )
    if store is not None:
        stmt = stmt.where(PlatformMonthStat.store == store)
    return session.exec(stmt).all()


@router.put("/platform-stats", response_model=PlatformMonthStatRead)
def upsert_platform_stat(
    payload: PlatformMonthStatUpsert,
    session: Session = Depends(get_session),
):
    existing = session.exec(
        select(PlatformMonthStat).where(
            PlatformMonthStat.store == payload.store,
            PlatformMonthStat.period_month == payload.period_month,
        )
    ).first()
    values = payload.model_dump(exclude={"store", "period_month"})
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        existing.updated_at = datetime.now(timezone.utc)
        record = existing
    else:
        record = PlatformMonthStat(
            store=payload.store, period_month=payload.period_month, **values
        )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


@router.delete("/platform-stats/{store}/{period_month}", status_code=204)
def delete_platform_stat(store: int, period_month: str, session: Session = Depends(get_session)):
    existing = session.exec(
        select(PlatformMonthStat).where(
            PlatformMonthStat.store == store,
            PlatformMonthStat.period_month == period_month,
        )
    ).first()
    if existing:
        session.delete(existing)
        session.commit()
    return None
