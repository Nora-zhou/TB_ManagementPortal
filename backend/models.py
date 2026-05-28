from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, Session, select, func
from sqlalchemy import UniqueConstraint


class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    status: str = Field(default="todo")      # todo | in_progress | done
    priority: str = Field(default="medium")  # low | medium | high
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    taobao_item_id: str = Field(unique=True, index=True, max_length=64)
    name: str = Field(max_length=500)
    url: Optional[str] = Field(default=None, max_length=1000)
    current_price: Optional[float] = None
    alert_low: Optional[float] = None
    alert_high: Optional[float] = None
    last_updated: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    store: int = Field(default=1)  # 1=店铺1, 2=店铺2


class PriceSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    price: float
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    store: int = Field(default=1)  # 1=店铺1, 2=店铺2


class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(unique=True, index=True, max_length=64)
    payment_id: Optional[str] = Field(default=None, max_length=64)
    payment_detail: Optional[str] = Field(default=None)
    total_amount: Optional[float] = None
    buyer_paid: Optional[float] = None
    status: Optional[str] = Field(default=None, max_length=64)
    created_at: Optional[datetime] = None
    product_title: Optional[str] = Field(default=None)
    seller_fee: Optional[float] = None
    refund_amount: Optional[float] = None
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    store: int = Field(default=1)  # 1=店铺1, 2=店铺2


class SubOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sub_order_id: str = Field(unique=True, index=True, max_length=64)
    main_order_id: str = Field(max_length=64)
    taobao_item_id: str = Field(index=True, max_length=64)
    product_title: str = Field(max_length=500)
    product_price: Optional[float] = None
    quantity: int = Field(default=1)
    product_attr: Optional[str] = Field(default=None, max_length=500)
    status: str = Field(max_length=64)
    payment_id: Optional[str] = Field(default=None, max_length=64)
    buyer_paid: float
    refund_amount: str = Field(max_length=64)
    created_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    store: int = Field(default=1)  # 1=店铺1, 2=店铺2


class PurchaseOrder(SQLModel, table=True):
    id:            Optional[int]      = Field(default=None, primary_key=True)
    order_id:      str                = Field(unique=True, index=True, max_length=64)
    seller_name:   str                = Field(index=True, max_length=200)
    seller_member: Optional[str]      = Field(default=None, max_length=200)
    goods_title:   Optional[str]      = Field(default=None, max_length=500)
    goods_total:   Optional[float]    = None
    unit_price:    Optional[float]    = None   # 单价(元) — per-unit purchase price
    quantity:      Optional[int]      = None   # 数量 — units purchased
    shipping_fee:  Optional[float]    = None
    discount:      Optional[float]    = None
    paid_amount:   float
    status:        str                = Field(max_length=64)
    created_at:    Optional[datetime] = None
    paid_at:       Optional[datetime] = None
    imported_at:   datetime           = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    store:         int                = Field(default=1)  # 1=店铺1, 2=店铺2


# ---------------------------------------------------------------------------
# 010-product-profit-analysis: SKU cost table
# ---------------------------------------------------------------------------

class ProductSKUCost(SQLModel, table=True):
    id:             Optional[int] = Field(default=None, primary_key=True)
    taobao_item_id: str           = Field(index=True, max_length=64)
    sku_id:         str           = Field(max_length=500)   # == SubOrder.product_attr; "" for single-SKU
    sku_name:       str           = Field(max_length=500)   # human-readable label (user-editable)
    purchase_cost:  float         = Field(ge=0.0)           # RMB / unit; non-negative

    __table_args__ = (UniqueConstraint("taobao_item_id", "sku_id"),)


def trim_snapshots(session: Session, product_id: int, limit: int = 365) -> None:
    """Delete oldest snapshots beyond `limit` for the given product."""
    count = session.exec(
        select(func.count()).where(PriceSnapshot.product_id == product_id)
    ).one()
    if count > limit:
        excess = count - limit
        oldest = session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.product_id == product_id)
            .order_by(PriceSnapshot.recorded_at.asc())
            .limit(excess)
        ).all()
        for snap in oldest:
            session.delete(snap)
