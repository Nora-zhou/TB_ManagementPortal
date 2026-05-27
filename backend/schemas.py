from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


VALID_STATUSES = {"todo", "in_progress", "done"}
VALID_PRIORITIES = {"low", "medium", "high"}


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[str] = Field(default=None, pattern="^(todo|in_progress|done)$")
    priority: Optional[str] = Field(default=None, pattern="^(low|medium|high)$")


class TaskRead(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: str
    priority: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Product schemas
# ---------------------------------------------------------------------------

class ProductRead(BaseModel):
    id: int
    taobao_item_id: str
    name: str
    url: Optional[str]
    current_price: Optional[float]
    alert_low: Optional[float]
    alert_high: Optional[float]
    last_updated: Optional[datetime]
    alert_status: str  # "normal" | "below_low" | "above_high"
    snapshot_count: Optional[int] = None
    sold_90d: int = 0

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ProductRead]


class AlertUpdate(BaseModel):
    alert_low: Optional[float] = None
    alert_high: Optional[float] = None


class AlertResponse(BaseModel):
    id: int
    alert_low: Optional[float]
    alert_high: Optional[float]


class TaobaoImportRequest(BaseModel):
    session_key: str
    app_key: str
    app_secret: str


class ImportResponse(BaseModel):
    imported: int
    updated: int
    errors: list[str]


# ---------------------------------------------------------------------------
# SubOrder schemas (005-product-order-price-trend)
# ---------------------------------------------------------------------------

class SubOrderImportResult(BaseModel):
    imported: int
    updated: int
    skipped: int
    errors: list[str]


class OrderPricePoint(BaseModel):
    created_at: datetime
    buyer_paid: float
    quantity: int
    product_attr: Optional[str]
    sub_order_id: str


# ---------------------------------------------------------------------------
# SupplierDashboard schemas (007-supplier-dashboard)
# ---------------------------------------------------------------------------

class TopSupplierItem(BaseModel):
    seller_name: str
    total_amount: float
    total_orders: int


class SupplierMonthlyItem(BaseModel):
    seller_name: str
    monthly_orders: dict[str, int]
    monthly_amounts: dict[str, float]


class SupplierDashboardResponse(BaseModel):
    top_suppliers: list[TopSupplierItem]
    months: list[str]
    monthly_data: list[SupplierMonthlyItem]


class OrderPriceSeriesResponse(BaseModel):
    product_id: int
    taobao_item_id: str
    days: Optional[int]
    total: int
    truncated: bool
    points: list[OrderPricePoint]


class GoodsDirImportResponse(BaseModel):
    imported: int
    updated: int
    errors: list[dict]  # [{"file": str, "reason": str}]


# ---------------------------------------------------------------------------
# Snapshot schemas
# ---------------------------------------------------------------------------

class SnapshotRead(BaseModel):
    id: int
    price: float
    recorded_at: datetime

    model_config = {"from_attributes": True}


class SnapshotTriggerRequest(BaseModel):
    session_key: str
    app_key: str
    app_secret: str


class SnapshotError(BaseModel):
    taobao_item_id: str
    reason: str


class SnapshotTriggerResponse(BaseModel):
    updated: int
    failed: int
    errors: list[SnapshotError]
    recorded_at: datetime


# ---------------------------------------------------------------------------
# Order schemas
# ---------------------------------------------------------------------------

class OrderRead(BaseModel):
    id: int
    order_id: str
    payment_id: Optional[str]
    total_amount: Optional[float]
    buyer_paid: Optional[float]
    status: Optional[str]
    created_at: Optional[datetime]
    product_title: Optional[str]
    seller_fee: Optional[float]
    refund_amount: Optional[float]
    imported_at: datetime
    store: int = 1

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[OrderRead]


class ImportResult(BaseModel):
    imported: int
    updated: int
    skipped: int
    errors: list[str]


class ImportProgress(BaseModel):
    status: str  # "idle" | "running"
    processed: Optional[int] = None
    total: Optional[int] = None
    percent: Optional[int] = None


class SummaryStats(BaseModel):
    total_orders: int
    success_orders: int
    total_revenue: float
    total_refund: float
    refund_rate: float
    avg_order_value: float
    date_min: Optional[str]
    date_max: Optional[str]


class TrendResponse(BaseModel):
    granularity: str
    labels: list[str]
    revenue: list[float]
    refund: list[float]
    order_count: list[int]


class StatusDistItem(BaseModel):
    status: str
    count: int
    percent: float


class TopProductItem(BaseModel):
    rank: int
    taobao_item_id: str
    product_title: str
    order_count: int
    total_revenue: float
    avg_price: float


class TopProductsResponse(BaseModel):
    sort_by: str
    items: list[TopProductItem]


# ---------------------------------------------------------------------------
# PurchaseOrder schemas (006-supplier-management)
# ---------------------------------------------------------------------------

class PurchaseOrderImportResult(BaseModel):
    imported: int
    updated: int
    errors: int


class AvailableMonth(BaseModel):
    year: int
    month: int


class SupplierSummaryItem(BaseModel):
    seller_name: str
    order_count: int
    total_paid: float
    top_goods: Optional[str] = None


class SupplierSummaryResponse(BaseModel):
    year: int
    month: int
    month_total: float
    items: list[SupplierSummaryItem]


class PurchaseOrderDetail(BaseModel):
    order_id: str
    goods_title: Optional[str] = None
    paid_amount: float
    status: str
    created_at: Optional[datetime] = None
    store: int = 1

    model_config = {"from_attributes": True}


class PurchaseOrderDetailResponse(BaseModel):
    seller_name: str
    year: int
    month: int
    page: int
    page_size: int
    total: int
    items: list[PurchaseOrderDetail]
