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


# ---------------------------------------------------------------------------
# 012-pure-profit-rpa: 平台账号凭据 / RPA 任务 / 抓取到的平台费用
# ---------------------------------------------------------------------------

# 支持的平台标识
PLATFORMS = ("qianniu", "alimama")

# 各平台可抓取的数据集（前端「选择拉取哪个数据」的选项来源）
PLATFORM_DATASETS: dict[str, list[dict]] = {
    "qianniu": [
        {"key": "platform_fee", "label": "平台扣费（技术服务费 / 佣金等）", "category": "platform_fee"},
        {"key": "shipping_insurance", "label": "运费险 / 订单险", "category": "shipping_insurance"},
        {"key": "order_fee_detail", "label": "订单级卖家服务费", "category": "platform_fee"},
    ],
    "alimama": [
        {"key": "promotion_ztc", "label": "直通车花费", "category": "promotion"},
        {"key": "promotion_mofang", "label": "引力魔方花费", "category": "promotion"},
        {"key": "promotion_wanxiangtai", "label": "万相台花费", "category": "promotion"},
        {"key": "promotion_other", "label": "其它推广（淘宝客 / 超级推荐）", "category": "promotion"},
    ],
}

# 费用类别（对应纯利润公式的扣减项）
EXPENSE_CATEGORIES = ("platform_fee", "promotion", "shipping_insurance", "other")

# RPA 任务状态机
RPA_TASK_STATUSES = ("pending", "running", "success", "failed", "cancelled", "need_verify")


class PlatformAccount(SQLModel, table=True):
    """平台登录账号（千牛 / 阿里妈妈）。

    密码以 Fernet 对称加密存储，密钥来自 .env 的 RPA_MASTER_KEY；
    数据库文件本身不做加密，请勿将 tasks.db 提交到版本库。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str = Field(max_length=32, index=True)      # qianniu | alimama
    account_label: str = Field(max_length=200)            # 用户自定义名称
    username: str = Field(max_length=200)                 # 登录名（明文，展示需要）
    password_enc: str                                     # 密码密文
    extra_enc: Optional[str] = None                       # 其它敏感信息密文
    store: int = Field(default=1)                         # 关联店铺 1/2
    last_login_at: Optional[datetime] = None
    last_login_status: str = Field(default="unknown")     # ok | fail | need_verify | unknown
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RPATask(SQLModel, table=True):
    """一次 RPA 抓取任务。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str = Field(max_length=32, index=True)
    account_id: int = Field(foreign_key="platformaccount.id", index=True)
    store: int = Field(default=1)
    datasets: str = Field(default="[]")                   # JSON: ["platform_fee", ...]
    period_month: Optional[str] = Field(default=None, max_length=7)  # YYYY-MM（可选）
    status: str = Field(default="pending", index=True)
    progress: int = Field(default=0)
    log: Optional[str] = None
    result_summary: Optional[str] = None                  # JSON
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StorePlatformExpense(SQLModel, table=True):
    """按「店铺 × 月份 × 类别」记录的额外费用（推广费 / 平台扣费 / 运费险等）。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    store: int = Field(index=True)
    period_month: str = Field(max_length=7, index=True)   # YYYY-MM
    category: str = Field(max_length=32, index=True)      # platform_fee | promotion | shipping_insurance | other
    sub_category: Optional[str] = Field(default=None, max_length=200)  # 直通车 / 引力魔方 / ...
    amount: float = Field(default=0.0)
    source: str = Field(default="manual")                 # rpa | manual | xlsx
    rpa_task_id: Optional[int] = None
    note: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("store", "period_month", "category", "sub_category"),)


class SessionCookie(SQLModel, table=True):
    """平台会话 Cookie 缓存（当前 Playwright 使用持久化 profile 自行管理，
    此表保留用于展示「登录态有效期」与未来切换到 API 直连时使用）。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="platformaccount.id", index=True)
    domain: str = Field(max_length=200)
    cookies_json_enc: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_valid: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
