import io
from datetime import datetime

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session, select
from typing import Annotated

from database import get_session
from models import SubOrder
from schemas import SubOrderImportResult

router = APIRouter(prefix="/sub-orders", tags=["sub-orders"])

SessionDep = Annotated[Session, Depends(get_session)]

_REQUIRED_COLUMNS = {
    "子订单编号", "主订单编号", "商品ID", "商品标题",
    "购买数量", "商品价格", "商品属性", "订单状态",
    "支付单号", "买家实付金额", "退款金额", "订单创建时间", "订单付款时间",
}


def _parse_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def _parse_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


@router.post("/import", response_model=SubOrderImportResult)
async def import_sub_orders(
    session: SessionDep,
    file: UploadFile = File(...),
    store: int = Form(...),
) -> SubOrderImportResult:
    if store not in (1, 2):
        raise HTTPException(status_code=422, detail="store 必须为 1 或 2")
    # 1. File type check
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=415, detail="仅支持 .xlsx 格式文件")

    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception:
        raise HTTPException(status_code=422, detail="无法解析 xlsx 文件，请确认文件未损坏")

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=422, detail="无法解析 xlsx 文件，请确认文件未损坏")

    # 2. Header row is first row
    raw_headers = rows[0]
    headers = [str(h).strip() if h is not None else "" for h in raw_headers]

    missing_cols = _REQUIRED_COLUMNS - set(headers)
    if missing_cols:
        raise HTTPException(
            status_code=422,
            detail=f"文件缺少必填列：{sorted(missing_cols)}",
        )

    col = {name: idx for idx, name in enumerate(headers)}

    imported = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for row_num, row in enumerate(rows[1:], start=2):
        taobao_item_id = str(row[col["商品ID"]]).strip() if row[col["商品ID"]] is not None else ""
        if not taobao_item_id or taobao_item_id.lower() in ("none", ""):
            errors.append(f"第 {row_num} 行：商品ID 为空，已跳过")
            continue

        buyer_paid_raw = row[col["买家实付金额"]]
        buyer_paid = _parse_float(buyer_paid_raw)
        if buyer_paid is None:
            # Empty paid amount is valid for closed/cancelled orders — treat as 0
            s = str(buyer_paid_raw).strip() if buyer_paid_raw is not None else ""
            if s == "" or s.lower() == "none":
                buyer_paid = 0.0
            else:
                errors.append(f"第 {row_num} 行：买家实付金额 '{buyer_paid_raw}' 无法解析，已跳过")
                continue

        sub_order_id = str(row[col["子订单编号"]]).strip() if row[col["子订单编号"]] is not None else ""
        main_order_id = str(row[col["主订单编号"]]).strip() if row[col["主订单编号"]] is not None else ""
        product_title = str(row[col["商品标题"]]).strip() if row[col["商品标题"]] is not None else ""

        qty_raw = row[col["购买数量"]]
        try:
            quantity = int(str(qty_raw).strip()) if qty_raw is not None else 1
        except (ValueError, TypeError):
            quantity = 1

        product_price = _parse_float(row[col["商品价格"]])
        product_attr_val = row[col["商品属性"]]
        product_attr = str(product_attr_val).strip() if product_attr_val is not None else None

        status_val = str(row[col["订单状态"]]).strip() if row[col["订单状态"]] is not None else ""
        payment_id_val = row[col["支付单号"]]
        payment_id = str(payment_id_val).strip() if payment_id_val is not None else None

        refund_val = row[col["退款金额"]]
        refund_amount = str(refund_val).strip() if refund_val is not None else ""

        created_at = _parse_datetime(row[col["订单创建时间"]])
        paid_at = _parse_datetime(row[col["订单付款时间"]])

        existing = session.exec(
            select(SubOrder).where(SubOrder.sub_order_id == sub_order_id)
        ).first()

        if existing:
            existing.main_order_id = main_order_id
            existing.taobao_item_id = taobao_item_id
            existing.product_title = product_title
            existing.product_price = product_price
            existing.quantity = quantity
            existing.product_attr = product_attr
            existing.status = status_val
            existing.payment_id = payment_id
            existing.buyer_paid = buyer_paid
            existing.refund_amount = refund_amount
            existing.created_at = created_at
            existing.paid_at = paid_at
            existing.store = store
            session.add(existing)
            updated += 1
        else:
            new_sub_order = SubOrder(
                sub_order_id=sub_order_id,
                main_order_id=main_order_id,
                taobao_item_id=taobao_item_id,
                product_title=product_title,
                product_price=product_price,
                quantity=quantity,
                product_attr=product_attr,
                status=status_val,
                payment_id=payment_id,
                buyer_paid=buyer_paid,
                refund_amount=refund_amount,
                created_at=created_at,
                paid_at=paid_at,
                store=store,
            )
            session.add(new_sub_order)
            imported += 1

    session.commit()

    return SubOrderImportResult(
        imported=imported,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )
