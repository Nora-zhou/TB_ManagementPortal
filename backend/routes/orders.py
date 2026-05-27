from __future__ import annotations

import io
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

import openpyxl
from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import Float as SAFloat
from sqlalchemy import cast as sa_cast
from sqlmodel import Session, col, func, select

from database import get_session
from models import Order, SubOrder
from schemas import (
    ImportProgress,
    ImportResult,
    OrderListResponse,
    OrderRead,
    StatusDistItem,
    SummaryStats,
    TopProductItem,
    TopProductsResponse,
    TrendResponse,
)

router = APIRouter(prefix="/orders", tags=["orders"])

# Module-level progress tracker (single-user tool — no concurrency concern)
_import_progress: dict = {"status": "idle"}
_import_lock = threading.Lock()

# Required xlsx column names
REQUIRED_COLUMNS = {
    "订单编号", "支付单号", "支付详情", "总金额",
    "买家实付金额", "订单状态", "订单创建时间",
    "商品标题", "卖家服务费", "退款金额",
}


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None


def _to_datetime(val) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.strptime(str(val).strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# POST /api/orders/import
# ---------------------------------------------------------------------------

@router.post("/import", response_model=ImportResult, status_code=status.HTTP_200_OK)
async def import_orders(
    file: UploadFile,
    store: int = Form(...),
    session: Session = Depends(get_session),
):
    if store not in (1, 2):
        raise HTTPException(status_code=422, detail="store 必须为 1 或 2")
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 .xlsx 格式文件",
        )

    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无法解析 xlsx 文件，请确认文件未损坏",
        )

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="文件内容为空",
        )

    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    missing = REQUIRED_COLUMNS - set(header)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"文件缺少必填列：{sorted(missing)}",
        )

    col_idx = {name: header.index(name) for name in REQUIRED_COLUMNS}
    data_rows = rows[1:]
    total = len(data_rows)

    # Reset progress
    _import_progress.update({"status": "running", "processed": 0, "total": total, "percent": 0})

    imported = updated = skipped = 0
    errors: list[str] = []

    for i, row in enumerate(data_rows):
        try:
            order_id = str(row[col_idx["订单编号"]]).strip() if row[col_idx["订单编号"]] else None
            if not order_id:
                skipped += 1
                continue

            existing = session.exec(
                select(Order).where(Order.order_id == order_id)
            ).first()

            values = {
                "order_id": order_id,
                "payment_id": str(row[col_idx["支付单号"]]).strip() if row[col_idx["支付单号"]] else None,
                "payment_detail": str(row[col_idx["支付详情"]]).strip() if row[col_idx["支付详情"]] else None,
                "total_amount": _to_float(row[col_idx["总金额"]]),
                "buyer_paid": _to_float(row[col_idx["买家实付金额"]]),
                "status": str(row[col_idx["订单状态"]]).strip() if row[col_idx["订单状态"]] else None,
                "created_at": _to_datetime(row[col_idx["订单创建时间"]]),
                "product_title": str(row[col_idx["商品标题"]]).strip() if row[col_idx["商品标题"]] else None,
                "seller_fee": _to_float(row[col_idx["卖家服务费"]]),
                "refund_amount": _to_float(row[col_idx["退款金额"]]),
                "store": store,
            }

            if existing:
                for k, v in values.items():
                    setattr(existing, k, v)
                existing.imported_at = datetime.now(timezone.utc)
                session.add(existing)
                updated += 1
            else:
                session.add(Order(**values))
                imported += 1

        except Exception as exc:
            errors.append(f"第 {i + 2} 行：{exc}")

        # Update progress every 50 rows
        if (i + 1) % 50 == 0:
            pct = int((i + 1) / total * 100)
            _import_progress.update({"processed": i + 1, "percent": pct})

    session.commit()
    _import_progress.update({"status": "idle"})

    return ImportResult(imported=imported, updated=updated, skipped=skipped, errors=errors)


# ---------------------------------------------------------------------------
# GET /api/orders/import/progress
# ---------------------------------------------------------------------------

@router.get("/import/progress", response_model=ImportProgress)
def get_import_progress():
    p = _import_progress
    if p["status"] == "idle":
        return ImportProgress(status="idle")
    return ImportProgress(
        status="running",
        processed=p.get("processed", 0),
        total=p.get("total", 0),
        percent=p.get("percent", 0),
    )


# ---------------------------------------------------------------------------
# POST /api/orders/sync-from-sub-orders
# ---------------------------------------------------------------------------

@router.post("/sync-from-sub-orders", response_model=ImportResult, status_code=status.HTTP_200_OK)
def sync_orders_from_sub_orders(session: Session = Depends(get_session)):
    """Aggregate SubOrder records by main_order_id to populate the Order table."""
    from collections import defaultdict

    sub_orders = session.exec(select(SubOrder)).all()
    if not sub_orders:
        return ImportResult(imported=0, updated=0, skipped=0, errors=["子订单表为空，请先导入子订单数据"])

    groups: dict[str, list[SubOrder]] = defaultdict(list)
    for so in sub_orders:
        groups[so.main_order_id].append(so)

    imported = updated = skipped = 0
    errors: list[str] = []

    for main_order_id, items in groups.items():
        if not main_order_id:
            skipped += 1
            continue

        # Aggregate fields
        buyer_paid_total = sum(i.buyer_paid or 0.0 for i in items)
        total_amount = sum((i.product_price or 0.0) * (i.quantity or 1) for i in items)
        # Parse refund amounts where possible
        refund_total = 0.0
        for i in items:
            try:
                v = float(str(i.refund_amount).strip())
                refund_total += v
            except (ValueError, TypeError):
                pass
        titles = "，".join({i.product_title for i in items if i.product_title})
        status_val = items[0].status
        payment_id = items[0].payment_id
        created_at = min((i.created_at for i in items if i.created_at), default=None)
        store_val = items[0].store

        existing = session.exec(
            select(Order).where(Order.order_id == main_order_id)
        ).first()

        values = {
            "order_id": main_order_id,
            "payment_id": payment_id,
            "payment_detail": None,
            "total_amount": total_amount,
            "buyer_paid": buyer_paid_total,
            "status": status_val,
            "created_at": created_at,
            "product_title": titles[:500] if titles else None,
            "seller_fee": None,
            "refund_amount": refund_total,
            "store": store_val,
        }

        try:
            if existing:
                for k, v in values.items():
                    setattr(existing, k, v)
                existing.imported_at = datetime.now(timezone.utc)
                session.add(existing)
                updated += 1
            else:
                session.add(Order(**values))
                imported += 1
        except Exception as exc:
            errors.append(f"订单 {main_order_id}：{exc}")

    session.commit()
    return ImportResult(imported=imported, updated=updated, skipped=skipped, errors=errors)


# ---------------------------------------------------------------------------
# GET /api/orders
# ---------------------------------------------------------------------------

SORTABLE_FIELDS = {"created_at", "buyer_paid", "refund_amount"}


@router.get("", response_model=OrderListResponse)
def list_orders(
    session: Session = Depends(get_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=5000),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    store: Optional[int] = Query(default=None),
):
    if sort_by not in SORTABLE_FIELDS:
        sort_by = "created_at"

    stmt = select(Order)
    count_stmt = select(func.count()).select_from(Order)

    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
        count_stmt = count_stmt.where(Order.status == status_filter)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(col(Order.product_title).like(pattern))
        count_stmt = count_stmt.where(col(Order.product_title).like(pattern))
    if start_date:
        try:
            dt_start = datetime.strptime(start_date, "%Y-%m-%d")
            stmt = stmt.where(Order.created_at >= dt_start)
            count_stmt = count_stmt.where(Order.created_at >= dt_start)
        except ValueError:
            pass
    if end_date:
        try:
            from datetime import timedelta
            dt_end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            stmt = stmt.where(Order.created_at < dt_end)
            count_stmt = count_stmt.where(Order.created_at < dt_end)
        except ValueError:
            pass
    if store is not None:
        stmt = stmt.where(Order.store == store)
        count_stmt = count_stmt.where(Order.store == store)

    order_col = getattr(Order, sort_by)
    stmt = stmt.order_by(order_col.asc() if sort_dir == "asc" else order_col.desc())

    total = session.exec(count_stmt).one()
    items = session.exec(stmt.offset((page - 1) * page_size).limit(page_size)).all()

    return OrderListResponse(total=total, page=page, page_size=page_size, items=items)


# ---------------------------------------------------------------------------
# GET /api/orders/stats/summary
# ---------------------------------------------------------------------------

@router.get("/stats/summary", response_model=SummaryStats)
def order_summary(
    session: Session = Depends(get_session),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    store: Optional[int] = Query(default=None),
):
    from datetime import timedelta

    def _apply_date_filter(stmt):
        if start_date:
            try:
                stmt = stmt.where(SubOrder.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
            except ValueError:
                pass
        if end_date:
            try:
                stmt = stmt.where(SubOrder.created_at < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
            except ValueError:
                pass
        if store is not None:
            stmt = stmt.where(SubOrder.store == store)
        return stmt

    total_orders = session.exec(
        _apply_date_filter(select(func.count(func.distinct(SubOrder.main_order_id))).select_from(SubOrder))
    ).one()
    success_orders = session.exec(
        _apply_date_filter(
            select(func.count(func.distinct(SubOrder.main_order_id)))
            .select_from(SubOrder)
            .where(SubOrder.status == "交易成功")
        )
    ).one()

    revenue_result = session.exec(
        _apply_date_filter(
            select(func.coalesce(func.sum(SubOrder.buyer_paid), 0.0))
        )
    ).one()
    total_revenue = float(revenue_result or 0.0)

    refund_result = session.exec(
        _apply_date_filter(
            select(func.coalesce(func.sum(sa_cast(SubOrder.refund_amount, SAFloat)), 0.0))
        )
    ).one()
    total_refund = float(refund_result or 0.0)

    refund_rate = round(total_refund / total_revenue, 4) if total_revenue > 0 else 0.0
    avg_order_value = round(total_revenue / total_orders, 2) if total_orders > 0 else 0.0

    # Date range
    date_min_row = session.exec(_apply_date_filter(select(func.min(SubOrder.created_at)))).one()
    date_max_row = session.exec(_apply_date_filter(select(func.max(SubOrder.created_at)))).one()
    date_min = str(date_min_row)[:10] if date_min_row else None
    date_max = str(date_max_row)[:10] if date_max_row else None

    return SummaryStats(
        total_orders=total_orders,
        success_orders=success_orders,
        total_revenue=round(total_revenue, 2),
        total_refund=round(total_refund, 2),
        refund_rate=refund_rate,
        avg_order_value=avg_order_value,
        date_min=date_min,
        date_max=date_max,
    )


# ---------------------------------------------------------------------------
# GET /api/orders/stats/trend
# ---------------------------------------------------------------------------

STRFTIME_MAP = {
    "day": "%Y-%m-%d",
    "week": "%Y-W%W",
    "month": "%Y-%m",
}


@router.get("/stats/trend", response_model=TrendResponse)
def order_trend(
    session: Session = Depends(get_session),
    granularity: Literal["day", "week", "month"] = Query(default="day"),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    store: Optional[int] = Query(default=None),
):
    fmt = STRFTIME_MAP[granularity]

    # Revenue (all orders)
    rev_stmt = (
        select(
            func.strftime(fmt, SubOrder.created_at).label("period"),
            func.coalesce(func.sum(SubOrder.buyer_paid), 0.0).label("revenue"),
            func.count(func.distinct(SubOrder.main_order_id)).label("cnt"),
        )
        .group_by(func.strftime(fmt, SubOrder.created_at))
        .order_by(func.strftime(fmt, SubOrder.created_at))
    )

    # Refund (all orders)
    ref_stmt = (
        select(
            func.strftime(fmt, SubOrder.created_at).label("period"),
            func.coalesce(func.sum(sa_cast(SubOrder.refund_amount, SAFloat)), 0.0).label("refund"),
        )
        .group_by(func.strftime(fmt, SubOrder.created_at))
        .order_by(func.strftime(fmt, SubOrder.created_at))
    )

    if start_date:
        try:
            dt = datetime.strptime(start_date, "%Y-%m-%d")
            rev_stmt = rev_stmt.where(SubOrder.created_at >= dt)
            ref_stmt = ref_stmt.where(SubOrder.created_at >= dt)
        except ValueError:
            pass
    if end_date:
        try:
            from datetime import timedelta
            dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            rev_stmt = rev_stmt.where(SubOrder.created_at < dt)
            ref_stmt = ref_stmt.where(SubOrder.created_at < dt)
        except ValueError:
            pass
    if store is not None:
        rev_stmt = rev_stmt.where(SubOrder.store == store)
        ref_stmt = ref_stmt.where(SubOrder.store == store)

    rev_rows = session.exec(rev_stmt).all()
    ref_rows = session.exec(ref_stmt).all()

    # Build label union
    all_labels = sorted(set(r.period for r in rev_rows) | set(r.period for r in ref_rows))
    rev_map = {r.period: (float(r.revenue), int(r.cnt)) for r in rev_rows}
    ref_map = {r.period: float(r.refund) for r in ref_rows}

    labels = all_labels
    revenue = [round(rev_map.get(l, (0.0, 0))[0], 2) for l in labels]
    refund = [round(ref_map.get(l, 0.0), 2) for l in labels]
    order_count = [rev_map.get(l, (0.0, 0))[1] for l in labels]

    return TrendResponse(
        granularity=granularity,
        labels=labels,
        revenue=revenue,
        refund=refund,
        order_count=order_count,
    )


# ---------------------------------------------------------------------------
# GET /api/orders/stats/status
# ---------------------------------------------------------------------------

@router.get("/stats/status", response_model=list[StatusDistItem])
def order_status_dist(
    session: Session = Depends(get_session),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    store: Optional[int] = Query(default=None),
):
    from datetime import timedelta

    stmt = (
        select(SubOrder.status, func.count(SubOrder.id).label("cnt"))
        .group_by(SubOrder.status)
        .order_by(func.count(SubOrder.id).desc())
    )
    if start_date:
        try:
            stmt = stmt.where(SubOrder.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
        except ValueError:
            pass
    if end_date:
        try:
            stmt = stmt.where(SubOrder.created_at < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            pass
    if store is not None:
        stmt = stmt.where(SubOrder.store == store)

    rows = session.exec(stmt).all()

    total = sum(r.cnt for r in rows)
    return [
        StatusDistItem(
            status=r.status or "未知",
            count=r.cnt,
            percent=round(r.cnt / total * 100, 2) if total else 0.0,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /api/orders/stats/top-products
# ---------------------------------------------------------------------------

@router.get("/stats/top-products", response_model=TopProductsResponse)
def top_products(
    session: Session = Depends(get_session),
    sort_by: Literal["revenue", "count"] = Query(default="revenue"),
    limit: int = Query(default=10, ge=1, le=50),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    store: Optional[int] = Query(default=None),
):
    from datetime import timedelta

    agg_stmt = (
        select(
            SubOrder.taobao_item_id,
            SubOrder.product_title,
            func.sum(SubOrder.buyer_paid).label("revenue"),
            func.count(SubOrder.id).label("cnt"),
        )
        .where(SubOrder.status == "交易成功")
        .group_by(SubOrder.taobao_item_id, SubOrder.product_title)
    )
    if start_date:
        try:
            agg_stmt = agg_stmt.where(SubOrder.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
        except ValueError:
            pass
    if end_date:
        try:
            agg_stmt = agg_stmt.where(SubOrder.created_at < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
        except ValueError:
            pass
    if store is not None:
        agg_stmt = agg_stmt.where(SubOrder.store == store)

    rows = session.exec(agg_stmt).all()

    key_fn = (lambda x: float(x.revenue or 0)) if sort_by == "revenue" else (lambda x: int(x.cnt))
    top = sorted(rows, key=key_fn, reverse=True)[:limit]

    items = [
        TopProductItem(
            rank=i + 1,
            taobao_item_id=r.taobao_item_id or "",
            product_title=r.product_title or "未知",
            order_count=int(r.cnt),
            total_revenue=round(float(r.revenue or 0), 2),
            avg_price=round(float(r.revenue or 0) / int(r.cnt), 2) if int(r.cnt) else 0.0,
        )
        for i, r in enumerate(top)
    ]

    return TopProductsResponse(sort_by=sort_by, items=items)
