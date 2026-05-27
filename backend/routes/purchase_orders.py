from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Optional

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

    return SupplierDashboardResponse(
        top_suppliers=top_suppliers,
        months=all_months,
        monthly_data=monthly_data,
    )
