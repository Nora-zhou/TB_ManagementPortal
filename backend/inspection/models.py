"""013 检测模块数据模型。

分层原则（见 specs/013-store-inspection/plan.md）：
- **事实层**（只增不改）：inspection_run / item_snapshot / assertion_result
- **判定层**（可重算）：metric / score / inspection_report

判定层带 rule_version / template_ver，规则改动后可对历史 run 重算做回归。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 枚举常量（不建独立表，值域固定且代码内校验） ──────────────────────────
SUBJECTS = ("self", "client", "competitor")
RUN_STATUSES = ("running", "ok", "partial", "failed")
RUN_SCOPES = ("shop", "item")
SOURCES = ("api", "page_xhr", "page_dom")
LEVELS = ("normal", "watch", "alert")
SCORE_DIMS = ("material", "title", "detail", "price", "review", "traffic", "profit")

# 采集字段分级：CORE 任一缺失即判定本次采集失败；ENHANCED 允许缺省
CORE_FIELDS = ("title", "price_cents", "image_count", "detail_image_count")
ENHANCED_FIELDS = (
    "sales_parsed",
    "review_count",
    "rating",
    "sku_json",
    "image_meta_json",
    "detail_meta_json",
    "review_json",
    "service_json",
    "stock_total",
    "item_status",
)


class InspectionRun(SQLModel, table=True):
    """一次检测运行（scope=shop 时为整店批量，scope=item 时为单商品）。"""

    __tablename__ = "inspection_run"

    id: Optional[int] = Field(default=None, primary_key=True)
    store: int = Field(default=1, index=True)
    subject: str = Field(default="self", max_length=32)      # self | client | competitor
    subject_name: Optional[str] = Field(default=None, max_length=200)
    run_id: str = Field(unique=True, index=True, max_length=64)
    scope: str = Field(default="item", max_length=16)         # shop | item
    item_target: Optional[int] = None
    item_success: Optional[int] = None
    status: str = Field(default="running", max_length=16)     # running | ok | partial | failed
    started_at: Optional[datetime] = Field(default_factory=_now)
    finished_at: Optional[datetime] = None


class ItemSnapshot(SQLModel, table=True):
    """商品页快照。事实层：只增不改，原始响应落 data/raw/<run_id>/。"""

    __tablename__ = "item_snapshot"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, max_length=64)
    item_id: str = Field(index=True, max_length=64)

    # ── 核心字段（CORE） ──
    title: Optional[str] = Field(default=None, max_length=500)
    price_cents: Optional[int] = None
    image_count: Optional[int] = None
    image_urls: Optional[str] = None                          # JSON: [url, ...]
    detail_image_count: Optional[int] = None

    # ── 价格结构 ──
    price_min_cents: Optional[int] = None
    price_max_cents: Optional[int] = None
    promo_price_cents: Optional[int] = None                   # 券后 / 促销价

    # ── 库存与状态 ──
    stock_total: Optional[int] = None
    item_status: Optional[str] = Field(default=None, max_length=16)  # onsale | offsale | soldout

    # ── 销售与评价（原文 + 结构） ──
    sales_text: Optional[str] = Field(default=None, max_length=200)
    sales_parsed: Optional[int] = None
    review_count: Optional[int] = None
    rating: Optional[float] = None
    review_json: Optional[str] = None                         # JSON: {count,neg_count,...}

    # ── 明细结构（JSON 文本） ──
    sku_json: Optional[str] = None                            # [{sku_id,name,price_cents,stock,img}]
    image_meta_json: Optional[str] = None                     # [{url,w,h,ratio,is_white_bg,has_text}]
    detail_meta_json: Optional[str] = None                    # {img_count,total_height,text_len,has_video}
    service_json: Optional[str] = None                        # {free_ship,shipping_insurance,ship_hours}
    detail_text: Optional[str] = None

    # ── 溯源与可信度 ──
    raw_path: Optional[str] = Field(default=None, max_length=1000)
    source: str = Field(default="page_dom", max_length=16)    # api | page_xhr | page_dom
    reliable: int = Field(default=1)                          # 整条记录级：1 可用 / 0 不可信
    field_reliable_json: Optional[str] = None                 # 字段级：{"price_cents": 1, ...}
    collected_at: datetime = Field(default_factory=_now)


class AssertionResult(SQLModel, table=True):
    """断言结果。passed=0 的字段在下游指标计算中被跳过。"""

    __tablename__ = "assertion_result"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, max_length=64)
    item_id: Optional[str] = Field(default=None, index=True, max_length=64)
    rule_id: str = Field(max_length=64)                       # PRICE_POSITIVE / IMAGE_COUNT_MIN ...
    passed: int = Field(default=1)
    actual: Optional[str] = Field(default=None, max_length=500)
    expected: Optional[str] = Field(default=None, max_length=500)
    message: Optional[str] = Field(default=None, max_length=500)


class Metric(SQLModel, table=True):
    """判定层：指标值 / 基线 / 偏离，可随时重算。"""

    __tablename__ = "metric"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, max_length=64)
    scope: str = Field(default="run", max_length=16)          # run | item | shop
    scope_key: Optional[str] = Field(default=None, max_length=64)
    name: str = Field(max_length=64)                          # sell_through / top10_share / ...
    value: Optional[float] = None
    baseline: Optional[float] = None
    baseline_type: Optional[str] = Field(default=None, max_length=32)
    deviation: Optional[float] = None
    level: str = Field(default="normal", max_length=16)       # normal | watch | alert


class Score(SQLModel, table=True):
    """判定层：七维评分。evidence 存 JSON，说明「为什么是这个分」。"""

    __tablename__ = "score"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, max_length=64)
    scope: str = Field(default="run", max_length=16)
    scope_key: Optional[str] = Field(default=None, max_length=64)
    dim: str = Field(max_length=16)                           # material|title|detail|price|review|traffic|profit
    points: float = Field(default=0.0)
    max_points: float = Field(default=0.0)
    evidence: Optional[str] = None                            # JSON
    rule_version: str = Field(default="v1", max_length=32)


class InspectionReport(SQLModel, table=True):
    """报告产物登记。"""

    __tablename__ = "inspection_report"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(unique=True, index=True, max_length=64)
    total_score: Optional[float] = None
    grade: Optional[str] = Field(default=None, max_length=16)
    html_path: Optional[str] = Field(default=None, max_length=1000)
    pdf_path: Optional[str] = Field(default=None, max_length=1000)
    template_ver: str = Field(default="v1", max_length=32)
    generated_at: datetime = Field(default_factory=_now)


TABLES = (
    InspectionRun,
    ItemSnapshot,
    AssertionResult,
    Metric,
    Score,
    InspectionReport,
)
