import csv
import io
import re
import openpyxl
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File, status
from sqlmodel import Session, select, func, col

from database import get_session
from models import Product, PriceSnapshot, SubOrder
from schemas import (
    AlertResponse,
    AlertUpdate,
    GoodsDirImportResponse,
    ImportResponse,
    OrderPricePoint,
    OrderPriceSeriesResponse,
    ProductListResponse,
    ProductRead,
    TaobaoImportRequest,
)
from taobao_client import fetch_store_items

GOODS_DIR = Path(__file__).parent.parent / "data" / "Goods"
GOODS_XLSX = Path(__file__).parent.parent / "data" / "Goods.xlsx"

router = APIRouter(prefix="/products", tags=["products"])

SessionDep = Annotated[Session, Depends(get_session)]

_REQUIRED_CSV_FIELDS = {"item_id", "name", "price", "url"}
_SAFE_URL_RE = re.compile(r'^https?://', re.IGNORECASE)


def _validate_url(url: Optional[str]) -> Optional[str]:
    """Return url if safe (http/https), else raise HTTPException."""
    if url and not _SAFE_URL_RE.match(url):
        raise HTTPException(
            status_code=422,
            detail=f"商品 URL 必须以 http:// 或 https:// 开头，实际值：{url[:80]}",
        )
    return url


def _compute_alert_status(product: Product) -> str:
    if product.current_price is None:
        return "normal"
    if product.alert_low is not None and product.current_price < product.alert_low:
        return "below_low"
    if product.alert_high is not None and product.current_price > product.alert_high:
        return "above_high"
    return "normal"


def _product_to_read(
    product: Product,
    session: Session,
    include_snapshot_count: bool = False,
    sold_90d: int = 0,
) -> ProductRead:
    snapshot_count = None
    if include_snapshot_count:
        snapshot_count = session.exec(
            select(func.count()).where(PriceSnapshot.product_id == product.id)
        ).one()
    return ProductRead(
        id=product.id,
        taobao_item_id=product.taobao_item_id,
        name=product.name,
        url=product.url,
        current_price=product.current_price,
        alert_low=product.alert_low,
        alert_high=product.alert_high,
        last_updated=product.last_updated,
        alert_status=_compute_alert_status(product),
        snapshot_count=snapshot_count,
        sold_90d=sold_90d,
    )


# ---------------------------------------------------------------------------
# POST /api/products/import/csv
# ---------------------------------------------------------------------------

@router.post("/import/csv", response_model=ImportResponse)
async def import_csv(
    session: SessionDep,
    file: UploadFile = File(...),
) -> ImportResponse:
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # handle BOM
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="文件编码不支持，请使用 UTF-8 编码的 CSV 文件")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=422, detail="CSV 文件为空或缺少标题行")

    missing = _REQUIRED_CSV_FIELDS - {f.strip() for f in reader.fieldnames}
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"CSV 缺少必填列：{', '.join(sorted(missing))}",
        )

    # --- Parse all rows first; abort entire import on any error (spec: atomic) ---
    rows_parsed: list[dict] = []
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):
        item_id = row.get("item_id", "").strip()
        name = row.get("name", "").strip()
        price_str = row.get("price", "").strip()
        raw_url = row.get("url", "").strip() or None

        if not item_id:
            errors.append(f"第 {row_num} 行：item_id 不能为空")
        elif not name:
            errors.append(f"第 {row_num} 行：name 不能为空")
        elif raw_url and not _SAFE_URL_RE.match(raw_url):  # C1 — reject javascript: etc.
            errors.append(f"第 {row_num} 行：url 必须以 http:// 或 https:// 开头")
        else:
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                errors.append(f"第 {row_num} 行：price 字段 '{price_str}' 不是有效数字")
                continue
            if price < 0:  # L1 — reject negative prices
                errors.append(f"第 {row_num} 行：price 不能为负数（{price}）")
                continue
            rows_parsed.append({"item_id": item_id, "name": name, "price": price, "url": raw_url})

    # H3 — abort entirely if any row has an error
    if errors:
        raise HTTPException(status_code=422, detail=errors[0])

    imported = updated = 0
    now = datetime.now(timezone.utc)
    for r in rows_parsed:
        existing = session.exec(
            select(Product).where(Product.taobao_item_id == r["item_id"])
        ).first()
        if existing:
            existing.name = r["name"]
            existing.url = r["url"]
            existing.current_price = r["price"]
            existing.last_updated = now
            session.add(existing)
            updated += 1
        else:
            session.add(Product(
                taobao_item_id=r["item_id"],
                name=r["name"],
                url=r["url"],
                current_price=r["price"],
                last_updated=now,
            ))
            imported += 1

    session.commit()
    return ImportResponse(imported=imported, updated=updated, errors=[])


# ---------------------------------------------------------------------------
# POST /api/products/import/goods-xlsx
# ---------------------------------------------------------------------------
# Goods.xlsx 格式（淘宝后台导出）：
#   第1行：注意事项；第2行：分组标题；第3行：字段名（实际表头）；第4行起：数据
#   关键列：商品Id → item_id, 宝贝标题 → name, 一口价 → price
#   同一商品Id 出现多行（每 SKU 一行），以第一次出现为准去重。
# ---------------------------------------------------------------------------

@router.post("/import/goods-xlsx", response_model=ImportResponse)
async def import_goods_xlsx(
    session: SessionDep,
    file: UploadFile = File(...),
    store: int = Form(...),
) -> ImportResponse:
    if store not in (1, 2):
        raise HTTPException(status_code=422, detail="store 必须为 1 或 2")
    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"无法解析 Excel 文件：{exc}")

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 3:
        raise HTTPException(status_code=422, detail="文件格式错误：至少需要 3 行表头 + 数据行")

    # Row 3 (index 2) is the real field header row
    headers = [str(h).strip() if h is not None else "" for h in rows[2]]
    try:
        idx_id = headers.index("商品Id")
        idx_name = headers.index("宝贝标题")
        idx_price = headers.index("一口价")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"文件缺少必要列：{exc}")

    seen: set[str] = set()
    to_upsert: list[dict] = []
    errors: list[str] = []

    for row_num, row in enumerate(rows[3:], start=4):
        item_id = str(row[idx_id]).strip() if row[idx_id] is not None else ""
        if not item_id or item_id in seen:
            continue  # skip empty or duplicate SKU rows
        seen.add(item_id)

        name = str(row[idx_name]).strip() if row[idx_name] is not None else ""
        price_raw = row[idx_price]
        try:
            price = float(str(price_raw).strip())
            if price < 0:
                errors.append(f"第 {row_num} 行 商品Id={item_id}：价格不能为负数")
                continue
        except (ValueError, TypeError):
            errors.append(f"第 {row_num} 行 商品Id={item_id}：一口价 '{price_raw}' 不是有效数字")
            continue

        url = f"https://item.taobao.com/item.htm?id={item_id}"
        to_upsert.append({"item_id": item_id, "name": name, "price": price, "url": url})

    if errors:
        raise HTTPException(status_code=422, detail=errors[0])

    imported = updated = 0
    now = datetime.now(timezone.utc)
    for r in to_upsert:
        existing = session.exec(
            select(Product).where(Product.taobao_item_id == r["item_id"])
        ).first()
        if existing:
            existing.name = r["name"]
            existing.current_price = r["price"]
            existing.url = r["url"]
            existing.last_updated = now
            existing.store = store
            session.add(existing)
            updated += 1
        else:
            session.add(Product(
                taobao_item_id=r["item_id"],
                name=r["name"],
                url=r["url"],
                current_price=r["price"],
                last_updated=now,
                store=store,
            ))
            imported += 1

    session.commit()
    return ImportResponse(imported=imported, updated=updated, errors=[])


# ---------------------------------------------------------------------------
# POST /api/products/import/from-goods-dir
# ---------------------------------------------------------------------------

@router.post("/import/from-goods-dir", response_model=GoodsDirImportResponse)
def import_from_goods_dir(
    session: SessionDep,
    store: int = Query(...),
) -> GoodsDirImportResponse:
    """Scan data/Goods/ directory (CSV + xlsx) and data/Goods.xlsx, upsert incrementally."""
    if store not in (1, 2):
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=422, detail="store 必须为 1 或 2")
    errors: list[dict] = []
    imported = updated = 0
    now = datetime.now(timezone.utc)

    # Collect all source files: CSVs in data/Goods/, xlsx files in data/Goods/, and data/Goods.xlsx
    csv_files: list[Path] = []
    xlsx_files: list[Path] = []

    if GOODS_DIR.exists():
        csv_files = sorted(GOODS_DIR.glob("*.csv"))
        xlsx_files = sorted(GOODS_DIR.glob("*.xlsx"))

    # Fallback: use data/Goods.xlsx if no files found in directory
    if not csv_files and not xlsx_files and GOODS_XLSX.exists():
        xlsx_files = [GOODS_XLSX]

    if not csv_files and not xlsx_files:
        return GoodsDirImportResponse(
            imported=0, updated=0,
            errors=[{"file": "", "reason": "Goods 目录下未找到 CSV/xlsx 文件"}],
        )

    def _upsert(item_id: str, name: str, price: float | None, url: str | None) -> str:
        """Return 'imported' or 'updated'."""
        nonlocal imported, updated
        existing = session.exec(
            select(Product).where(Product.taobao_item_id == item_id)
        ).first()
        if existing:
            existing.name = name or existing.name
            if price is not None:
                existing.current_price = price
            existing.url = url if url is not None else existing.url
            existing.last_updated = now
            existing.store = store
            session.add(existing)
            updated += 1
            return "updated"
        else:
            session.add(Product(
                taobao_item_id=item_id,
                name=name,
                url=url,
                current_price=price,
                last_updated=now,
                store=store,
            ))
            imported += 1
            return "imported"

    # --- Process CSV files ---
    for csv_path in csv_files:
        try:
            text = csv_path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            errors.append({"file": csv_path.name, "reason": f"无法读取文件：{exc}"})
            continue

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "item_id" not in {f.strip() for f in reader.fieldnames}:
            errors.append({"file": csv_path.name, "reason": "缺少必填列 item_id"})
            continue

        for row in reader:
            item_id = (row.get("item_id") or "").strip()
            if not item_id:
                continue
            name = (row.get("name") or "").strip()
            url = (row.get("url") or "").strip() or None
            if url and not _SAFE_URL_RE.match(url):
                url = None
            price_str = (row.get("price") or "").strip()
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                price = None
            _upsert(item_id, name, price, url)

    # --- Process xlsx files (淘宝 Goods.xlsx format) ---
    for xlsx_path in xlsx_files:
        try:
            wb = openpyxl.load_workbook(str(xlsx_path), data_only=True)
        except Exception as exc:
            errors.append({"file": xlsx_path.name, "reason": f"无法解析 xlsx 文件：{exc}"})
            continue

        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 3:
            errors.append({"file": xlsx_path.name, "reason": "文件格式错误：至少需要 3 行表头 + 数据行"})
            continue

        # Row 3 (index 2) is the real field header row in Taobao export
        headers = [str(h).strip() if h is not None else "" for h in rows[2]]
        try:
            idx_id = headers.index("商品Id")
            idx_name = headers.index("宝贝标题")
            idx_price = headers.index("一口价")
        except ValueError as exc:
            errors.append({"file": xlsx_path.name, "reason": f"文件缺少必要列：{exc}"})
            continue

        seen: set[str] = set()
        for row in rows[3:]:
            item_id = str(row[idx_id]).strip() if row[idx_id] is not None else ""
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            name = str(row[idx_name]).strip() if row[idx_name] is not None else ""
            price_raw = row[idx_price]
            try:
                price: float | None = float(str(price_raw).strip())
                if price < 0:
                    price = None
            except (ValueError, TypeError):
                price = None
            url = f"https://item.taobao.com/item.htm?id={item_id}"
            _upsert(item_id, name, price, url)

    session.commit()
    return GoodsDirImportResponse(imported=imported, updated=updated, errors=errors)


# ---------------------------------------------------------------------------
# POST /api/products/import/taobao
# ---------------------------------------------------------------------------

@router.post("/import/taobao", response_model=ImportResponse)
async def import_taobao(
    payload: TaobaoImportRequest,
    session: SessionDep,
) -> ImportResponse:
    try:
        items = await fetch_store_items(
            session_key=payload.session_key,
            app_key=payload.app_key,
            app_secret=payload.app_secret,
        )
    except ValueError as exc:
        error_msg = str(exc)
        if "无效" in error_msg or "invalid" in error_msg.lower() or "session" in error_msg.lower():
            raise HTTPException(status_code=401, detail="淘宝 Token 无效，请重新授权")
        raise HTTPException(status_code=502, detail=f"连接淘宝开放平台失败：{error_msg}")
    except Exception:
        raise HTTPException(status_code=502, detail="连接淘宝开放平台失败，请检查网络或稍后重试")

    imported = updated = 0
    errors: list[str] = []

    for item in items:
        item_id = str(item["item_id"])
        existing = session.exec(
            select(Product).where(Product.taobao_item_id == item_id)
        ).first()
        price = item.get("price")
        if existing:
            existing.name = item.get("title", existing.name)
            if price is not None:
                existing.current_price = price
                existing.last_updated = datetime.now(timezone.utc)
            session.add(existing)
            updated += 1
        else:
            product = Product(
                taobao_item_id=item_id,
                name=item.get("title", ""),
                current_price=price,
                last_updated=datetime.now(timezone.utc) if price is not None else None,
            )
            session.add(product)
            imported += 1

    session.commit()
    return ImportResponse(imported=imported, updated=updated, errors=errors)


# ---------------------------------------------------------------------------
# GET /api/products
# ---------------------------------------------------------------------------

@router.get("", response_model=ProductListResponse)
def list_products(
    session: SessionDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: Optional[str] = Query(default=None),
    min_price: Optional[float] = Query(default=None),
    max_price: Optional[float] = Query(default=None),
) -> ProductListResponse:
    query = select(Product)
    if q:
        query = query.where(col(Product.name).contains(q))
    if min_price is not None:
        query = query.where(Product.current_price >= min_price)
    if max_price is not None:
        query = query.where(Product.current_price <= max_price)

    total = session.exec(
        select(func.count()).select_from(query.subquery())
    ).one()

    products = session.exec(
        query.order_by(Product.last_updated.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    # Batch-aggregate sold_90d from SubOrder in one query (avoid N+1).
    # Falls back to empty dict if SubOrder table doesn't exist yet (spec 005 not imported).
    cutoff = datetime.now() - timedelta(days=90)
    item_ids = [p.taobao_item_id for p in products]
    try:
        rows = session.exec(
            select(SubOrder.taobao_item_id, func.sum(SubOrder.quantity))
            .where(
                col(SubOrder.taobao_item_id).in_(item_ids),
                SubOrder.status == "交易成功",
                SubOrder.refund_amount == "无退款申请",
                SubOrder.paid_at >= cutoff,
            )
            .group_by(SubOrder.taobao_item_id)
        ).all()
        sold_map: dict[str, int] = {tid: (qty or 0) for tid, qty in rows}
    except Exception:
        sold_map = {}

    return ProductListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            _product_to_read(p, session, sold_90d=sold_map.get(p.taobao_item_id, 0))
            for p in products
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/products/{id}
# ---------------------------------------------------------------------------

@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, session: SessionDep) -> ProductRead:
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_read(product, session, include_snapshot_count=True)


# ---------------------------------------------------------------------------
# PUT /api/products/{id}/alert
# ---------------------------------------------------------------------------

@router.put("/{product_id}/alert", response_model=AlertResponse)
def update_alert(
    product_id: int,
    payload: AlertUpdate,
    session: SessionDep,
) -> AlertResponse:
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.alert_low = payload.alert_low
    product.alert_high = payload.alert_high
    session.add(product)
    session.commit()
    session.refresh(product)
    return AlertResponse(id=product.id, alert_low=product.alert_low, alert_high=product.alert_high)


# ---------------------------------------------------------------------------
# DELETE /api/products/{id}
# ---------------------------------------------------------------------------

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, session: SessionDep) -> None:
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    # cascade-delete snapshots
    snapshots = session.exec(
        select(PriceSnapshot).where(PriceSnapshot.product_id == product_id)
    ).all()
    for snap in snapshots:
        session.delete(snap)
    session.delete(product)
    session.commit()


# ---------------------------------------------------------------------------
# GET /api/products/{id}/order-price-series
# ---------------------------------------------------------------------------

@router.get("/{product_id}/order-price-series", response_model=OrderPriceSeriesResponse)
def get_order_price_series(
    product_id: int,
    session: SessionDep,
    days: Optional[str] = Query(default=None),
) -> OrderPriceSeriesResponse:
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    days_int: Optional[int] = None
    if days in ("30", "90"):
        days_int = int(days)

    query = (
        select(SubOrder)
        .where(SubOrder.taobao_item_id == product.taobao_item_id)
        .where(SubOrder.status == "交易成功")
        .where(SubOrder.refund_amount == "无退款申请")
    )

    if days_int is not None:
        cutoff = datetime.now() - timedelta(days=days_int)
        query = query.where(SubOrder.created_at >= cutoff)

    all_matching = session.exec(query.order_by(SubOrder.created_at.asc())).all()
    total = len(all_matching)
    truncated = total > 1000
    points_data = all_matching[:1000]

    points = [
        OrderPricePoint(
            created_at=s.created_at,
            buyer_paid=s.buyer_paid,
            quantity=s.quantity,
            product_attr=s.product_attr,
            sub_order_id=s.sub_order_id,
        )
        for s in points_data
    ]

    return OrderPriceSeriesResponse(
        product_id=product_id,
        taobao_item_id=product.taobao_item_id,
        days=days_int,
        total=total,
        truncated=truncated,
        points=points,
    )

