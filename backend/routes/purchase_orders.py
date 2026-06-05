from __future__ import annotations

import io
import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case as sql_case, distinct

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, Form, status
from sqlmodel import Session, func, select

from database import get_session
from models import PurchaseOrder
from schemas import (
    AvailableMonth,
    PurchaseOrderDetail,
    PurchaseOrderDetailResponse,
    PurchaseOrderImportResult,
    SupplierSummaryItem,
    SupplierSummaryResponse,
    TopSupplierItem,
    SupplierMonthlyItem,
    SupplierDashboardResponse,
    SupplierReturnRateItem,
    SupplierEvaluationItem,
    SupplierEvaluationResponse,
    ReturnRateGoodsItem,
    SupplierEvaluationDetail,
    RefundOrderItem,
)

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])

REQUIRED_COLUMNS = {"订单编号", "卖家公司名", "实付款(元)", "订单状态", "订单创建时间"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
# Statuses excluded from all statistics queries
EXCLUDED_STATUSES = ("等待买家付款", "退款中", "交易关闭")


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


def _cell(row, idx):
    """Safely retrieve a cell value by column index."""
    if idx is None or idx >= len(row):
        return None
    return row[idx]


# ---------------------------------------------------------------------------
# POST /api/purchase-orders/import
# ---------------------------------------------------------------------------

@router.post("/import", response_model=PurchaseOrderImportResult)
async def import_purchase_orders(
    file: UploadFile,
    store: int = Form(...),
    session: Session = Depends(get_session),
):
    if store not in (1, 2):
        raise HTTPException(status_code=422, detail="store 必须为 1 或 2")
    # 1. Read content first (needed for both size check and parsing)
    content = await file.read()

    # 2. File size check — 10 MB hard limit
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件过大，请检查")

    # 3. Extension check
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 .xlsx 格式",
        )

    # 4. Parse xlsx — do NOT use read_only=True; streaming mode mishandles
    #    shared-strings and merged headers in some 1688 exports.
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无法解析文件，请确认为有效 xlsx",
        )

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="文件内容为空",
        )

    # 5. Build column map — strip all header values to handle leading/trailing spaces
    raw_headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    col_map: dict[str, int] = {h: i for i, h in enumerate(raw_headers)}

    missing = REQUIRED_COLUMNS - set(col_map.keys())
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"缺少列：{', '.join(sorted(missing))}",
        )

    idx_order_id      = col_map["订单编号"]
    idx_seller_name   = col_map["卖家公司名"]
    idx_paid_amount   = col_map["实付款(元)"]
    idx_status        = col_map["订单状态"]
    idx_created_at    = col_map["订单创建时间"]
    idx_seller_member = col_map.get("卖家会员名")
    idx_goods_total   = col_map.get("货品总价(元)")
    idx_shipping_fee  = col_map.get("运费(元)")
    idx_discount      = col_map.get("涨价或折扣(元)")
    idx_paid_at       = col_map.get("订单付款时间")
    idx_goods_title   = col_map.get("货品标题")
    idx_unit_price    = col_map.get("单价(元)")
    idx_quantity      = col_map.get("数量")

    imported = 0
    updated = 0
    errors = 0

    for row in rows[1:]:
        # Skip continuation rows (order_id is None or empty)
        raw_order_id = _cell(row, idx_order_id)
        if raw_order_id is None or str(raw_order_id).strip() == "":
            continue

        order_id = str(raw_order_id).strip()

        # Parse paid_amount — skip and count error if not parseable
        paid_amount = _to_float(_cell(row, idx_paid_amount))
        if paid_amount is None:
            errors += 1
            continue

        # seller_name — default to '未知供应商' when empty
        raw_seller = _cell(row, idx_seller_name)
        seller_name = str(raw_seller).strip() if raw_seller else ""
        if not seller_name:
            seller_name = "未知供应商"

        # Optional fields
        sel_raw = _cell(row, idx_seller_member)
        seller_member = str(sel_raw).strip() if sel_raw else None

        goods_total  = _to_float(_cell(row, idx_goods_total))
        shipping_fee = _to_float(_cell(row, idx_shipping_fee))
        discount     = _to_float(_cell(row, idx_discount))
        unit_price   = _to_float(_cell(row, idx_unit_price))
        qty_raw      = _to_float(_cell(row, idx_quantity))
        quantity     = int(qty_raw) if qty_raw is not None else None

        status_raw = _cell(row, idx_status)
        status_val = str(status_raw).strip() if status_raw else ""

        created_at = _to_datetime(_cell(row, idx_created_at))
        paid_at    = _to_datetime(_cell(row, idx_paid_at))

        gt_raw = _cell(row, idx_goods_title)
        goods_title = str(gt_raw).strip()[:500] if gt_raw else None

        # Upsert by order_id
        existing = session.exec(
            select(PurchaseOrder).where(PurchaseOrder.order_id == order_id)
        ).first()

        if existing:
            existing.seller_name   = seller_name
            existing.seller_member = seller_member
            existing.goods_title   = goods_title
            existing.goods_total   = goods_total
            existing.unit_price    = unit_price
            existing.quantity      = quantity
            existing.shipping_fee  = shipping_fee
            existing.discount      = discount
            existing.paid_amount   = paid_amount
            existing.status        = status_val
            existing.created_at    = created_at
            existing.paid_at       = paid_at
            existing.imported_at   = datetime.now(timezone.utc)
            existing.store         = store
            session.add(existing)
            updated += 1
        else:
            session.add(PurchaseOrder(
                order_id      = order_id,
                seller_name   = seller_name,
                seller_member = seller_member,
                goods_title   = goods_title,
                goods_total   = goods_total,
                unit_price    = unit_price,
                quantity      = quantity,
                shipping_fee  = shipping_fee,
                discount      = discount,
                paid_amount   = paid_amount,
                status        = status_val,
                created_at    = created_at,
                paid_at       = paid_at,
                store         = store,
            ))
            imported += 1

    session.commit()
    return PurchaseOrderImportResult(imported=imported, updated=updated, errors=errors)


# ---------------------------------------------------------------------------
# GET /api/purchase-orders/months
# ---------------------------------------------------------------------------

@router.get("/months", response_model=list[AvailableMonth])
def get_available_months(
    session: Session = Depends(get_session),
):
    stmt = (
        select(
            func.strftime("%Y", PurchaseOrder.created_at).label("year"),
            func.strftime("%m", PurchaseOrder.created_at).label("month"),
        )
        .where(PurchaseOrder.created_at.isnot(None))
        .distinct()
        .order_by(
            func.strftime("%Y", PurchaseOrder.created_at).desc(),
            func.strftime("%m", PurchaseOrder.created_at).desc(),
        )
    )
    results = session.exec(stmt).all()
    return [AvailableMonth(year=int(r.year), month=int(r.month)) for r in results]


# ---------------------------------------------------------------------------
# Internal helper: top goods for a supplier in a given month
# ---------------------------------------------------------------------------

def _get_top_goods(
    session: Session,
    seller_name: str,
    year_str: str,
    month_str: str,
) -> Optional[str]:
    stmt = (
        select(
            PurchaseOrder.goods_title,
            func.count(PurchaseOrder.id).label("cnt"),
        )
        .where(
            PurchaseOrder.seller_name == seller_name,
            func.strftime("%Y", PurchaseOrder.created_at) == year_str,
            func.strftime("%m", PurchaseOrder.created_at) == month_str,
            PurchaseOrder.status.not_in(EXCLUDED_STATUSES),
            PurchaseOrder.created_at.isnot(None),
            PurchaseOrder.goods_title.isnot(None),
        )
        .group_by(PurchaseOrder.goods_title)
        .order_by(func.count(PurchaseOrder.id).desc())
        .limit(1)
    )
    row = session.exec(stmt).first()
    return row.goods_title if row else None


# ---------------------------------------------------------------------------
# GET /api/purchase-orders/summary
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=SupplierSummaryResponse)
def get_supplier_summary(
    year: int,
    month: int,
    store: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
):
    year_str  = str(year)
    month_str = f"{month:02d}"

    base_filters = [
        func.strftime("%Y", PurchaseOrder.created_at) == year_str,
        func.strftime("%m", PurchaseOrder.created_at) == month_str,
        PurchaseOrder.status.not_in(EXCLUDED_STATUSES),
        PurchaseOrder.created_at.isnot(None),
    ]
    if store is not None:
        base_filters.append(PurchaseOrder.store == store)

    stmt = (
        select(
            PurchaseOrder.seller_name,
            func.count(PurchaseOrder.id).label("order_count"),
            func.sum(PurchaseOrder.paid_amount).label("total_paid"),
        )
        .where(*base_filters)
        .group_by(PurchaseOrder.seller_name)
        .order_by(func.sum(PurchaseOrder.paid_amount).desc())
    )
    results = session.exec(stmt).all()

    month_total = float(session.exec(
        select(func.sum(PurchaseOrder.paid_amount)).where(*base_filters)
    ).one() or 0.0)

    items = []
    for r in results:
        top_goods = _get_top_goods(session, r.seller_name, year_str, month_str)
        items.append(SupplierSummaryItem(
            seller_name=r.seller_name,
            order_count=r.order_count,
            total_paid=float(r.total_paid or 0.0),
            top_goods=top_goods,
        ))

    return SupplierSummaryResponse(year=year, month=month, month_total=month_total, items=items)


# ---------------------------------------------------------------------------
# GET /api/purchase-orders/detail
# ---------------------------------------------------------------------------

@router.get("/detail", response_model=PurchaseOrderDetailResponse)
def get_supplier_detail(
    seller_name: str,
    year: int,
    month: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    year_str  = str(year)
    month_str = f"{month:02d}"

    filter_args = [
        PurchaseOrder.seller_name == seller_name,
        func.strftime("%Y", PurchaseOrder.created_at) == year_str,
        func.strftime("%m", PurchaseOrder.created_at) == month_str,
        PurchaseOrder.status.not_in(EXCLUDED_STATUSES),
        PurchaseOrder.created_at.isnot(None),
    ]

    total = session.exec(
        select(func.count(PurchaseOrder.id)).where(*filter_args)
    ).one()

    offset = (page - 1) * page_size
    records = session.exec(
        select(PurchaseOrder)
        .where(*filter_args)
        .offset(offset)
        .limit(page_size)
    ).all()

    items = [
        PurchaseOrderDetail(
            order_id    = r.order_id,
            goods_title = r.goods_title[:40] if r.goods_title else None,
            paid_amount = r.paid_amount,
            status      = r.status,
            created_at  = r.created_at,
        )
        for r in records
    ]

    return PurchaseOrderDetailResponse(
        seller_name = seller_name,
        year        = year,
        month       = month,
        page        = page,
        page_size   = page_size,
        total       = total,
        items       = items,
    )


# ---------------------------------------------------------------------------
# GET /api/purchase-orders/dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=SupplierDashboardResponse)
def get_supplier_dashboard(
    top_n: int = Query(default=15, ge=1, le=100),
    start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    end_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    store: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
):
    """Return Top-N suppliers by total paid_amount with per-month breakdowns."""
    base_filters = [
        PurchaseOrder.status.not_in(EXCLUDED_STATUSES),
        PurchaseOrder.created_at.isnot(None),
        PurchaseOrder.paid_amount.isnot(None),
    ]
    if store is not None:
        base_filters.append(PurchaseOrder.store == store)
    if start_month:
        base_filters.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) >= start_month
        )
    if end_month:
        base_filters.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) <= end_month
        )

    # Query 1: Top N suppliers by total paid_amount
    top_stmt = (
        select(
            PurchaseOrder.seller_name,
            func.sum(PurchaseOrder.paid_amount).label("total_amount"),
            func.count(PurchaseOrder.id).label("total_orders"),
        )
        .where(*base_filters)
        .group_by(PurchaseOrder.seller_name)
        .order_by(func.sum(PurchaseOrder.paid_amount).desc())
        .limit(top_n)
    )
    top_results = session.exec(top_stmt).all()

    if not top_results:
        return SupplierDashboardResponse(top_suppliers=[], months=[], monthly_data=[])

    top_suppliers = [
        TopSupplierItem(
            seller_name=r.seller_name,
            total_amount=float(r.total_amount or 0.0),
            total_orders=int(r.total_orders),
        )
        for r in top_results
    ]
    top_names = [s.seller_name for s in top_suppliers]

    # Query 2: Monthly breakdown for top N suppliers
    monthly_stmt = (
        select(
            PurchaseOrder.seller_name,
            func.strftime("%Y-%m", PurchaseOrder.created_at).label("month_key"),
            func.count(PurchaseOrder.id).label("order_count"),
            func.sum(PurchaseOrder.paid_amount).label("month_amount"),
        )
        .where(
            *base_filters,
            PurchaseOrder.seller_name.in_(top_names),
        )
        .group_by(
            PurchaseOrder.seller_name,
            func.strftime("%Y-%m", PurchaseOrder.created_at),
        )
        .order_by(
            func.strftime("%Y-%m", PurchaseOrder.created_at),
        )
    )
    monthly_results = session.exec(monthly_stmt).all()

    # Collect all months sorted ascending
    all_months = sorted({r.month_key for r in monthly_results})

    # Build per-supplier monthly data with zero-fill
    monthly_data = []
    for supplier in top_suppliers:
        orders_by_month: dict[str, int] = {}
        amounts_by_month: dict[str, float] = {}
        for r in monthly_results:
            if r.seller_name == supplier.seller_name:
                orders_by_month[r.month_key] = int(r.order_count)
                amounts_by_month[r.month_key] = float(r.month_amount or 0.0)
        monthly_orders = {m: orders_by_month.get(m, 0) for m in all_months}
        monthly_amounts = {m: amounts_by_month.get(m, 0.0) for m in all_months}
        monthly_data.append(SupplierMonthlyItem(
            seller_name=supplier.seller_name,
            monthly_orders=monthly_orders,
            monthly_amounts=monthly_amounts,
        ))

    # Query 3: Per-supplier return rate (top 15 by return rate, min 3 orders)
    rr_filters = [
        PurchaseOrder.status != "等待买家付款",
        PurchaseOrder.created_at.isnot(None),
    ]
    if store is not None:
        rr_filters.append(PurchaseOrder.store == store)
    if start_month:
        rr_filters.append(func.strftime("%Y-%m", PurchaseOrder.created_at) >= start_month)
    if end_month:
        rr_filters.append(func.strftime("%Y-%m", PurchaseOrder.created_at) <= end_month)

    rr_stmt = (
        select(
            PurchaseOrder.seller_name,
            func.count(PurchaseOrder.id).label("total_count"),
            func.sum(
                sql_case(
                    (
                        (PurchaseOrder.status == "退款中")
                        | ((PurchaseOrder.status == "交易关闭") & (PurchaseOrder.paid_amount > 0)),
                        1,
                    ),
                    else_=0,
                )
            ).label("return_count"),
        )
        .where(*rr_filters)
        .group_by(PurchaseOrder.seller_name)
    )
    rr_results = session.exec(rr_stmt).all()
    return_rate_suppliers = sorted(
        [
            SupplierReturnRateItem(
                seller_name=r.seller_name,
                return_rate=round(int(r.return_count or 0) / int(r.total_count) * 100, 2),
                return_count=int(r.return_count or 0),
                total_count=int(r.total_count),
            )
            for r in rr_results
            if int(r.total_count or 0) >= 3 and int(r.return_count or 0) > 0
        ],
        key=lambda x: -x.return_rate,
    )[:15]

    return SupplierDashboardResponse(
        top_suppliers=top_suppliers,
        months=all_months,
        monthly_data=monthly_data,
        return_rate_suppliers=return_rate_suppliers,
    )


# ---------------------------------------------------------------------------
# Part 2 helper functions (T012)
# ---------------------------------------------------------------------------

def _linear_slope(ys: list[float]) -> float:
    """OLS slope for a time series. Returns 0.0 if fewer than 2 points."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_x2 = sum(x * x for x in xs)
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def _months_in_window(
    start: Optional[str],
    end: Optional[str],
    db_min: Optional[str],
    db_max: Optional[str],
) -> int:
    """Return the number of natural months between start and end (inclusive)."""
    s = start or db_min
    e = end or db_max
    if s is None or e is None:
        return 1
    sy, sm = int(s[:4]), int(s[5:7])
    ey, em = int(e[:4]), int(e[5:7])
    return max((ey - sy) * 12 + (em - sm) + 1, 1)


def _score_label(score: Optional[float]) -> str:
    if score is None:
        return "数据不足"
    if score >= 85:
        return "优质供应商 ⭐⭐⭐"
    if score >= 65:
        return "稳定合作商 ⭐⭐"
    if score >= 45:
        return "一般供应商 ⭐"
    return "需关注 ⚠️"


# ---------------------------------------------------------------------------
# Part 2 core computation (T014)
# ---------------------------------------------------------------------------

def _compute_all_evaluations(
    session: Session,
    start_month: Optional[str],
    end_month: Optional[str],
) -> list[SupplierEvaluationItem]:
    """Compute evaluation scores for all suppliers in the given time window."""

    # Build optional date filters reused across all queries
    date_filters = []
    if start_month:
        date_filters.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) >= start_month
        )
    if end_month:
        date_filters.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) <= end_month
        )

    # Step 0: Global time window for activity denominator
    window_stmt = select(
        func.min(func.strftime("%Y-%m", PurchaseOrder.created_at)).label("db_min"),
        func.max(func.strftime("%Y-%m", PurchaseOrder.created_at)).label("db_max"),
    ).where(PurchaseOrder.created_at.isnot(None), *date_filters)
    window_row = session.exec(window_stmt).one()
    db_min = window_row.db_min
    db_max = window_row.db_max
    total_months = _months_in_window(start_month, end_month, db_min, db_max)

    # Step 1: Per-seller completion rate data
    # WHERE excludes only 等待买家付款; 退款中/交易关闭 stay in denominator
    # Numerator: 交易成功 + 等待卖家发货 + 等待买家确认收货 (fulfilled orders)
    _FULFILLED_STATUSES = ("交易成功", "等待卖家发货", "等待买家确认收货")
    stmt1 = (
        select(
            PurchaseOrder.seller_name,
            func.count(PurchaseOrder.id).label("denom"),
            func.sum(
                sql_case(
                    (PurchaseOrder.status.in_(_FULFILLED_STATUSES), 1),
                    else_=0,
                )
            ).label("numer"),
            func.sum(
                sql_case(
                    (
                        (PurchaseOrder.status == "交易成功")
                        & (PurchaseOrder.paid_amount.isnot(None)),
                        PurchaseOrder.paid_amount,
                    ),
                    else_=0,
                )
            ).label("total_amount"),
        )
        .where(
            PurchaseOrder.status != "等待买家付款",
            PurchaseOrder.created_at.isnot(None),
            *date_filters,
        )
        .group_by(PurchaseOrder.seller_name)
    )
    stmt1_results = session.exec(stmt1).all()

    if not stmt1_results:
        return []

    seller_stats: dict[str, dict] = {
        r.seller_name: {
            "denom": int(r.denom or 0),
            "numer": int(r.numer or 0),
            "total_amount": float(r.total_amount or 0.0),
        }
        for r in stmt1_results
    }

    # Step 2: Price stability — weighted CV per seller
    stmt2 = (
        select(
            PurchaseOrder.seller_name,
            PurchaseOrder.goods_title,
            func.avg(PurchaseOrder.unit_price).label("avg_price"),
            (
                func.avg(PurchaseOrder.unit_price * PurchaseOrder.unit_price)
                - func.avg(PurchaseOrder.unit_price) * func.avg(PurchaseOrder.unit_price)
            ).label("var_price"),
            func.sum(PurchaseOrder.paid_amount).label("total_paid"),
        )
        .where(
            PurchaseOrder.status == "交易成功",
            PurchaseOrder.unit_price.isnot(None),
            PurchaseOrder.goods_title.isnot(None),
            PurchaseOrder.created_at.isnot(None),
            *date_filters,
        )
        .group_by(PurchaseOrder.seller_name, PurchaseOrder.goods_title)
    )
    stmt2_results = session.exec(stmt2).all()

    stmt2_by_seller: dict[str, list] = {}
    for r in stmt2_results:
        stmt2_by_seller.setdefault(r.seller_name, []).append(r)

    seller_price_stability: dict[str, float] = {}
    for seller_name in seller_stats:
        rows = stmt2_by_seller.get(seller_name)
        if not rows:
            seller_price_stability[seller_name] = 0.0
            continue
        total_paid_sum = sum(float(r.total_paid or 0.0) for r in rows)
        if total_paid_sum <= 0:
            seller_price_stability[seller_name] = 0.0
            continue
        weighted_cv = 0.0
        for r in rows:
            avg_p = float(r.avg_price or 0.0)
            var_p = float(r.var_price or 0.0)
            std_p = math.sqrt(max(var_p, 0.0))
            cv = std_p / avg_p if avg_p > 0 else 0.0
            weighted_cv += float(r.total_paid or 0.0) * cv
        weighted_cv /= total_paid_sum
        seller_price_stability[seller_name] = max(0.0, (1.0 - weighted_cv) * 100.0)

    # Step 3: Activity rate — distinct active months per seller
    stmt3 = (
        select(
            PurchaseOrder.seller_name,
            func.count(
                distinct(func.strftime("%Y-%m", PurchaseOrder.created_at))
            ).label("active_months"),
        )
        .where(
            PurchaseOrder.status == "交易成功",
            PurchaseOrder.created_at.isnot(None),
            *date_filters,
        )
        .group_by(PurchaseOrder.seller_name)
    )
    stmt3_results = session.exec(stmt3).all()
    seller_activity: dict[str, int] = {
        r.seller_name: int(r.active_months or 0) for r in stmt3_results
    }

    # Step 4: Price trend — monthly weighted average unit price per seller
    stmt4 = (
        select(
            PurchaseOrder.seller_name,
            func.strftime("%Y-%m", PurchaseOrder.created_at).label("ym"),
            (
                func.sum(PurchaseOrder.unit_price * PurchaseOrder.quantity)
                / func.sum(PurchaseOrder.quantity)
            ).label("wavg_price"),
        )
        .where(
            PurchaseOrder.status == "交易成功",
            PurchaseOrder.unit_price.isnot(None),
            PurchaseOrder.quantity.isnot(None),
            PurchaseOrder.quantity > 0,
            PurchaseOrder.created_at.isnot(None),
            *date_filters,
        )
        .group_by(
            PurchaseOrder.seller_name,
            func.strftime("%Y-%m", PurchaseOrder.created_at),
        )
        .order_by(
            PurchaseOrder.seller_name,
            func.strftime("%Y-%m", PurchaseOrder.created_at),
        )
    )
    stmt4_results = session.exec(stmt4).all()

    seller_prices: dict[str, list[float]] = {}
    for r in stmt4_results:
        seller_prices.setdefault(r.seller_name, []).append(float(r.wavg_price or 0.0))

    all_slopes: dict[str, float] = {
        name: _linear_slope(seller_prices.get(name, []))
        for name in seller_stats
    }

    # Step 5: Map positive slopes to trend scores via percentile
    positive_slopes = [k for k in all_slopes.values() if k > 0]

    seller_trend_score: dict[str, float] = {}
    if len(positive_slopes) == 0:
        for name in seller_stats:
            seller_trend_score[name] = 100.0
    elif len(positive_slopes) == 1:
        for name, slope in all_slopes.items():
            seller_trend_score[name] = 0.0 if slope > 0 else 100.0
    else:
        k_min = min(positive_slopes)
        k_max = max(positive_slopes)
        for name, slope in all_slopes.items():
            if slope <= 0:
                seller_trend_score[name] = 100.0
            elif k_min == k_max:
                seller_trend_score[name] = 0.0
            else:
                seller_trend_score[name] = (1.0 - (slope - k_min) / (k_max - k_min)) * 100.0

    # Step 6 & 7: Compute final scores and sort
    results: list[SupplierEvaluationItem] = []
    for seller_name, stats in seller_stats.items():
        denom = stats["denom"]
        numer = stats["numer"]
        total_amount = stats["total_amount"]

        if denom < 3:
            results.append(SupplierEvaluationItem(
                seller_name=seller_name,
                score=None,
                label="数据不足",
                completion_rate=None,
                price_stability=None,
                activity_rate=None,
                price_trend_score=None,
                total_amount=total_amount,
                order_count=denom,
            ))
        else:
            completion_rate = numer / denom * 100.0
            price_stability = seller_price_stability.get(seller_name, 0.0)
            active_months = seller_activity.get(seller_name, 0)
            activity_rate = min(active_months / total_months * 100.0, 100.0)
            trend_score = seller_trend_score.get(seller_name, 100.0)
            score = round(
                completion_rate * 0.35
                + price_stability * 0.30
                + activity_rate * 0.20
                + trend_score * 0.15,
                2,
            )
            results.append(SupplierEvaluationItem(
                seller_name=seller_name,
                score=score,
                label=_score_label(score),
                completion_rate=round(completion_rate, 2),
                price_stability=round(price_stability, 2),
                activity_rate=round(activity_rate, 2),
                price_trend_score=round(trend_score, 2),
                total_amount=total_amount,
                order_count=denom,
            ))

    results.sort(key=lambda x: (x.score is None, -(x.score or 0.0)))
    return results


# ---------------------------------------------------------------------------
# GET /api/purchase-orders/evaluation  (T015)
# ---------------------------------------------------------------------------

@router.get("/evaluation", response_model=SupplierEvaluationResponse)
def get_supplier_evaluation(
    start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    end_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    items = _compute_all_evaluations(session, start_month, end_month)
    return SupplierEvaluationResponse(suppliers=items)


# ---------------------------------------------------------------------------
# GET /api/purchase-orders/evaluation/{seller_name}  (T016)
# ---------------------------------------------------------------------------

@router.get("/evaluation/{seller_name}", response_model=SupplierEvaluationDetail)
def get_supplier_evaluation_detail(
    seller_name: str,
    start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    end_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    session: Session = Depends(get_session),
):
    # 1. Existence check — seller_name via SQLModel bound parameter (NFR-E005)
    exists_stmt = (
        select(PurchaseOrder.seller_name)
        .where(PurchaseOrder.seller_name == seller_name)
        .limit(1)
    )
    exists_result = session.exec(exists_stmt).first()
    if not exists_result:
        raise HTTPException(status_code=404, detail="供应商不存在")

    # 2. Re-run full evaluation to ensure price_trend percentile consistency
    items = _compute_all_evaluations(session, start_month, end_month)
    target = next((item for item in items if item.seller_name == seller_name), None)
    if target is None:
        target = SupplierEvaluationItem(
            seller_name=seller_name,
            score=None,
            label=_score_label(None),
            completion_rate=None,
            price_stability=None,
            activity_rate=None,
            price_trend_score=None,
            total_amount=0.0,
            order_count=0,
        )

    # Date filters for price history queries
    date_filters = []
    if start_month:
        date_filters.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) >= start_month
        )
    if end_month:
        date_filters.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) <= end_month
        )

    # 3. Top 5 goods by return rate for this supplier
    # Return = 退款中 (ongoing) OR 交易关闭 with paid_amount > 0 (refund completed).
    # 交易关闭 with paid_amount = 0 are unpaid-timeout cancellations — excluded.
    # Note: paid_at is unreliable in 1688 exports (often null for closed orders),
    # so paid_amount > 0 is used as the proxy for "order was actually paid".
    return_stmt = (
        select(
            PurchaseOrder.goods_title,
            func.count(PurchaseOrder.id).label("total_count"),
            func.sum(
                sql_case(
                    (
                        (PurchaseOrder.status == "退款中")
                        | (
                            (PurchaseOrder.status == "交易关闭")
                            & (PurchaseOrder.paid_amount > 0)
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("return_count"),
        )
        .where(
            PurchaseOrder.seller_name == seller_name,
            PurchaseOrder.status != "等待买家付款",
            PurchaseOrder.goods_title.isnot(None),
            *date_filters,
        )
        .group_by(PurchaseOrder.goods_title)
    )
    return_results = session.exec(return_stmt).all()
    top_return_goods = sorted(
        [
            ReturnRateGoodsItem(
                goods_title=r.goods_title,
                return_rate=round(int(r.return_count or 0) / int(r.total_count) * 100, 2),
                return_count=int(r.return_count or 0),
                total_count=int(r.total_count),
            )
            for r in return_results
            if int(r.total_count or 0) > 0 and int(r.return_count or 0) > 0
        ],
        key=lambda x: -x.return_count,
    )[:5]

    return SupplierEvaluationDetail(
        seller_name=seller_name,
        score=target.score,
        label=target.label,
        dimensions={
            "completion_rate": target.completion_rate,
            "price_stability": target.price_stability,
            "activity_rate": target.activity_rate,
            "price_trend_score": target.price_trend_score,
        },
        top_return_goods=top_return_goods,
    )


@router.get("/refund-orders", response_model=list[RefundOrderItem])
def get_refund_orders(
    seller_name: str,
    goods_title: str,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Return all refund orders for a specific supplier + goods_title."""
    conditions = [
        PurchaseOrder.seller_name == seller_name,
        PurchaseOrder.goods_title == goods_title,
        (
            (PurchaseOrder.status == "退款中")
            | (
                (PurchaseOrder.status == "交易关闭")
                & (PurchaseOrder.paid_amount > 0)
            )
        ),
    ]
    if start_month:
        conditions.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) >= start_month
        )
    if end_month:
        conditions.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) <= end_month
        )
    stmt = (
        select(PurchaseOrder)
        .where(*conditions)
        .order_by(PurchaseOrder.created_at.desc())
    )
    rows = session.exec(stmt).all()
    return [
        RefundOrderItem(
            order_id=r.order_id,
            goods_title=r.goods_title,
            status=r.status,
            paid_amount=r.paid_amount,
            quantity=r.quantity,
            unit_price=r.unit_price,
            created_at=r.created_at.strftime("%Y-%m-%d") if r.created_at else None,
        )
        for r in rows
    ]


@router.get("/refund-orders-by-seller", response_model=list[RefundOrderItem])
def get_refund_orders_by_seller(
    seller_name: str,
    start_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    end_month: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    store: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
):
    """Return all orders (交易成功 + refund) for a specific seller across all goods."""
    conditions = [
        PurchaseOrder.seller_name == seller_name,
        PurchaseOrder.status != "\u7b49\u5f85\u4e70\u5bb6\u4ed8\u6b3e",
    ]
    if store is not None:
        conditions.append(PurchaseOrder.store == store)
    if start_month:
        conditions.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) >= start_month
        )
    if end_month:
        conditions.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) <= end_month
        )
    stmt = (
        select(PurchaseOrder)
        .where(*conditions)
        .order_by(PurchaseOrder.created_at.desc())
    )
    rows = session.exec(stmt).all()
    return [
        RefundOrderItem(
            order_id=r.order_id,
            goods_title=r.goods_title,
            status=r.status,
            paid_amount=r.paid_amount,
            quantity=r.quantity,
            unit_price=r.unit_price,
            created_at=r.created_at.strftime("%Y-%m-%d") if r.created_at else None,
        )
        for r in rows
    ]
    if store is not None:
        conditions.append(PurchaseOrder.store == store)
    if start_month:
        conditions.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) >= start_month
        )
    if end_month:
        conditions.append(
            func.strftime("%Y-%m", PurchaseOrder.created_at) <= end_month
        )
    stmt = (
        select(PurchaseOrder)
        .where(*conditions)
        .order_by(PurchaseOrder.created_at.desc())
    )
    rows = session.exec(stmt).all()
    return [
        RefundOrderItem(
            order_id=r.order_id,
            goods_title=r.goods_title,
            status=r.status,
            paid_amount=r.paid_amount,
            quantity=r.quantity,
            unit_price=r.unit_price,
            created_at=r.created_at.strftime("%Y-%m-%d") if r.created_at else None,
        )
        for r in rows
    ]
