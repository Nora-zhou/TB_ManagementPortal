import asyncio
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from database import get_session
from models import Product, PriceSnapshot, trim_snapshots
from schemas import SnapshotRead, SnapshotTriggerRequest, SnapshotTriggerResponse, SnapshotError
from taobao_client import fetch_item_price

router = APIRouter(tags=["snapshots"])

SessionDep = Annotated[Session, Depends(get_session)]

_snapshot_in_progress = False


# ---------------------------------------------------------------------------
# POST /api/snapshots  — trigger full price snapshot
# ---------------------------------------------------------------------------

@router.post("/snapshots", response_model=SnapshotTriggerResponse)
async def trigger_snapshot(
    payload: SnapshotTriggerRequest,
    session: SessionDep,
) -> SnapshotTriggerResponse:
    global _snapshot_in_progress
    if _snapshot_in_progress:
        raise HTTPException(status_code=409, detail="快照记录正在进行中，请稍候")

    _snapshot_in_progress = True
    try:
        products = session.exec(select(Product)).all()
        updated = 0
        errors: list[SnapshotError] = []
        now = datetime.now(timezone.utc)

        for product in products:
            try:
                price = await fetch_item_price(
                    item_id=product.taobao_item_id,
                    session_key=payload.session_key,
                    app_key=payload.app_key,
                    app_secret=payload.app_secret,
                )
                if price is None:
                    errors.append(SnapshotError(
                        taobao_item_id=product.taobao_item_id,
                        reason="商品无价格数据",
                    ))
                    continue
                snap = PriceSnapshot(
                    product_id=product.id,
                    price=price,
                    recorded_at=now,
                )
                session.add(snap)
                session.flush()  # get snap.id before trim
                trim_snapshots(session, product.id)
                product.current_price = price
                product.last_updated = now
                session.add(product)
                updated += 1
            except ValueError as exc:
                errors.append(SnapshotError(
                    taobao_item_id=product.taobao_item_id,
                    reason=str(exc),
                ))
            except Exception as exc:
                errors.append(SnapshotError(
                    taobao_item_id=product.taobao_item_id,
                    reason=f"获取价格失败：{exc}",
                ))

        session.commit()
        return SnapshotTriggerResponse(
            updated=updated,
            failed=len(errors),
            errors=errors,
            recorded_at=now,
        )
    finally:
        _snapshot_in_progress = False


# ---------------------------------------------------------------------------
# GET /api/products/{id}/snapshots
# ---------------------------------------------------------------------------

@router.get("/products/{product_id}/snapshots", response_model=list[SnapshotRead])
def get_snapshots(product_id: int, session: SessionDep) -> list[SnapshotRead]:
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    snapshots = session.exec(
        select(PriceSnapshot)
        .where(PriceSnapshot.product_id == product_id)
        .order_by(PriceSnapshot.recorded_at.asc())
    ).all()
    return [SnapshotRead(id=s.id, price=s.price, recorded_at=s.recorded_at) for s in snapshots]

