import csv
import io
import re
import openpyxl
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File, status
from sqlmodel import Session, select, func, col
from sqlalchemy import text, bindparam

from database import get_session
from models import Product, PriceSnapshot, SubOrder, ProductSKUCost
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
    ProductSKUCostRead,
    ProductSKUCostBatchRequest,
    ProductSKUCostSuggestResponse,
    ProductProfitSummary,
    ProductProfitMonthlyResponse,
    ProductProfitMonthly,
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
    gross_margin_pct: Optional[float] = None,
    sku_cost_configured: Optional[bool] = None,
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
        gross_margin_pct=gross_margin_pct,
        sku_cost_configured=sku_cost_configured,
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
    page_size: int = Query(default=20, ge=1, le=5000),
    q: Optional[str] = Query(default=None),
    min_price: Optional[float] = Query(default=None),
    max_price: Optional[float] = Query(default=None),
    store: Optional[int] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    sort_order: Optional[str] = Query(default="asc"),
) -> ProductListResponse:
    base_query = select(Product)
    if q:
        base_query = base_query.where(col(Product.name).contains(q))
    if min_price is not None:
        base_query = base_query.where(Product.current_price >= min_price)
    if max_price is not None:
        base_query = base_query.where(Product.current_price <= max_price)
    if store is not None:
        base_query = base_query.where(Product.store == store)

    def _batch_margin(item_ids: list[str]) -> dict[str, Optional[float]]:
        if not item_ids:
            return {}
        sql = text("""
            SELECT
                so.taobao_item_id,
                SUM(CASE WHEN so.status = '交易成功'
                         THEN so.buyer_paid ELSE 0.0 END) -
                SUM(CASE WHEN so.status = '交易成功'
                         THEN CAST(so.refund_amount AS REAL) ELSE 0.0 END) AS revenue,
                SUM(CASE WHEN so.status = '交易成功'
                         THEN so.quantity * COALESCE(psc.purchase_cost, 0.0)
                         ELSE 0.0 END) AS cost
            FROM suborder so
            LEFT JOIN productskucost psc
                ON  psc.taobao_item_id = so.taobao_item_id
                AND psc.sku_id         = COALESCE(so.product_attr, '')
            WHERE so.taobao_item_id IN :ids
            GROUP BY so.taobao_item_id
        """).bindparams(bindparam('ids', expanding=True))
        try:
            rows = session.execute(sql, {"ids": list(item_ids)}).fetchall()
        except Exception:
            return {}
        result: dict[str, Optional[float]] = {}
        for row in rows:
            rev = row[1] or 0.0
            cost = row[2] or 0.0
            result[row[0]] = round((rev - cost) / rev * 100, 2) if rev > 0 and cost > 0 else None
        return result

    def _batch_sku_cost_status(item_ids: list[str]) -> dict[str, bool]:
        """Return {taobao_item_id: True} if ALL SKUs have purchase_cost > 0, False otherwise."""
        if not item_ids:
            return {}
        sql = text("""
            SELECT
                so.taobao_item_id,
                COUNT(DISTINCT COALESCE(so.product_attr, '')) AS sku_count,
                COUNT(DISTINCT CASE
                    WHEN psc.purchase_cost IS NOT NULL AND psc.purchase_cost > 0
                    THEN COALESCE(so.product_attr, '')
                END) AS configured_count
            FROM suborder so
            LEFT JOIN productskucost psc
                ON  psc.taobao_item_id = so.taobao_item_id
                AND psc.sku_id         = COALESCE(so.product_attr, '')
            WHERE so.taobao_item_id IN :ids
            GROUP BY so.taobao_item_id
        """).bindparams(bindparam('ids', expanding=True))
        try:
            rows = session.execute(sql, {"ids": list(item_ids)}).fetchall()
        except Exception:
            return {}
        result: dict[str, bool] = {}
        for row in rows:
            sku_count = row[1] or 0
            configured_count = row[2] or 0
            if sku_count > 0:
                result[row[0]] = (sku_count == configured_count)
        return result

    def _batch_sold_90d(item_ids: list[str]) -> dict[str, int]:
        if not item_ids:
            return {}
        cutoff = datetime.now() - timedelta(days=90)
        try:
            sold_rows = session.exec(
                select(SubOrder.taobao_item_id, func.sum(SubOrder.quantity))
                .where(
                    col(SubOrder.taobao_item_id).in_(item_ids),
                    SubOrder.status == "交易成功",
                    SubOrder.refund_amount == "无退款申请",
                    SubOrder.paid_at >= cutoff,
                )
                .group_by(SubOrder.taobao_item_id)
            ).all()
            return {tid: (qty or 0) for tid, qty in sold_rows}
        except Exception:
            return {}

    sold_map: Optional[dict[str, int]] = None

    if sort_by == "gross_margin_pct":
        # Fetch all filtered products, compute margins, sort in Python, then slice
        all_products = session.exec(base_query).all()
        all_item_ids = [p.taobao_item_id for p in all_products]
        margin_map = _batch_margin(all_item_ids)

        def _margin_key(p: Product) -> float:
            v = margin_map.get(p.taobao_item_id)
            if v is None:
                return float('inf') if (sort_order or "asc") == "asc" else float('-inf')
            return v

        reverse = (sort_order or "asc") == "desc"
        sorted_all = sorted(all_products, key=_margin_key, reverse=reverse)
        total = len(sorted_all)
        products = sorted_all[(page - 1) * page_size: page * page_size]
        item_ids = [p.taobao_item_id for p in products]
        page_margin_map = {tid: margin_map.get(tid) for tid in item_ids}

    elif sort_by == "sold_90d":
        all_products = session.exec(base_query).all()
        all_item_ids = [p.taobao_item_id for p in all_products]
        all_sold_map = _batch_sold_90d(all_item_ids)

        reverse = (sort_order or "desc") == "desc"
        sorted_all = sorted(all_products, key=lambda p: all_sold_map.get(p.taobao_item_id, 0), reverse=reverse)
        total = len(sorted_all)
        products = sorted_all[(page - 1) * page_size: page * page_size]
        item_ids = [p.taobao_item_id for p in products]
        sold_map = {tid: all_sold_map.get(tid, 0) for tid in item_ids}
        page_margin_map = _batch_margin(item_ids)

    else:
        total = session.exec(
            select(func.count()).select_from(base_query.subquery())
        ).one()
        products = session.exec(
            base_query.order_by(Product.last_updated.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        item_ids = [p.taobao_item_id for p in products]
        page_margin_map = _batch_margin(item_ids)

    if sold_map is None:
        sold_map = _batch_sold_90d(item_ids)

    sku_cost_status_map = _batch_sku_cost_status(item_ids)

    return ProductListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            _product_to_read(
                p, session,
                sold_90d=sold_map.get(p.taobao_item_id, 0),
                gross_margin_pct=page_margin_map.get(p.taobao_item_id),
                sku_cost_configured=sku_cost_status_map.get(p.taobao_item_id),
            )
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


# ---------------------------------------------------------------------------
# 010-product-profit-analysis endpoints
# ---------------------------------------------------------------------------

def _get_product_or_404(product_id: int, session: Session) -> Product:
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# GET /api/products/{id}/sku-list  — distinct SKUs from sub-orders (for initialising the cost table)
@router.get("/{product_id}/sku-list")
def get_sku_list(product_id: int, session: SessionDep) -> list[dict]:
    product = _get_product_or_404(product_id, session)
    rows = session.execute(
        text("""
            SELECT DISTINCT
                COALESCE(product_attr, '')            AS sku_id,
                COALESCE(product_attr, '默认（无规格）') AS sku_name
            FROM suborder
            WHERE taobao_item_id = :item_id
            ORDER BY sku_id
        """),
        {"item_id": product.taobao_item_id},
    ).fetchall()
    return [{"sku_id": r[0], "sku_name": r[1]} for r in rows]


# GET /api/products/{id}/sku-costs
@router.get("/{product_id}/sku-costs", response_model=list[ProductSKUCostRead])
def get_sku_costs(product_id: int, session: SessionDep) -> list[ProductSKUCostRead]:
    product = _get_product_or_404(product_id, session)
    costs = session.exec(
        select(ProductSKUCost).where(ProductSKUCost.taobao_item_id == product.taobao_item_id)
    ).all()
    return [ProductSKUCostRead.model_validate(c) for c in costs]


# PUT /api/products/{id}/sku-costs
@router.put("/{product_id}/sku-costs", response_model=list[ProductSKUCostRead])
def upsert_sku_costs(
    product_id: int,
    payload: ProductSKUCostBatchRequest,
    session: SessionDep,
) -> list[ProductSKUCostRead]:
    product = _get_product_or_404(product_id, session)
    for item in payload.items:
        # INSERT OR REPLACE via SQLite dialect
        session.execute(
            text("""
                INSERT INTO productskucost (taobao_item_id, sku_id, sku_name, purchase_cost)
                VALUES (:taobao_item_id, :sku_id, :sku_name, :purchase_cost)
                ON CONFLICT(taobao_item_id, sku_id)
                DO UPDATE SET sku_name = excluded.sku_name,
                              purchase_cost = excluded.purchase_cost
            """),
            {
                "taobao_item_id": product.taobao_item_id,
                "sku_id": item.sku_id,
                "sku_name": item.sku_name,
                "purchase_cost": item.purchase_cost,
            },
        )
    session.commit()
    costs = session.exec(
        select(ProductSKUCost).where(ProductSKUCost.taobao_item_id == product.taobao_item_id)
    ).all()
    return [ProductSKUCostRead.model_validate(c) for c in costs]


# GET /api/products/{id}/sku-cost-suggest
@router.get("/{product_id}/sku-cost-suggest", response_model=ProductSKUCostSuggestResponse)
def suggest_sku_cost(product_id: int, session: SessionDep) -> ProductSKUCostSuggestResponse:
    product = _get_product_or_404(product_id, session)

    # Try progressively shorter keyword prefixes until a match is found.
    # Split on spaces/punctuation and try the longest token first, then fall
    # back to the first 6 / 4 characters of the product name.
    import re as _re
    name = product.name or ""
    tokens = [t for t in _re.split(r"[\s\u3000\uff0c\u3001\uff08\uff09\u300a\u300b]+", name) if len(t) >= 2]
    candidates = tokens + ([name[:6]] if len(name) >= 6 else []) + ([name[:4]] if len(name) >= 4 else [])
    # deduplicate while preserving order
    seen_kw: set = set()
    keywords = []
    for k in candidates:
        if k not in seen_kw:
            seen_kw.add(k)
            keywords.append(k)

    avg_cost, matched = None, 0
    for kw in keywords:
        pattern = f"%{kw}%"
        row = session.execute(
            text("""
                SELECT
                    -- Prefer unit_price; fall back to goods_total/quantity; last resort goods_total
                    AVG(
                        CASE
                            WHEN unit_price IS NOT NULL AND unit_price > 0
                                THEN unit_price
                            WHEN quantity IS NOT NULL AND quantity > 0 AND goods_total IS NOT NULL
                                THEN goods_total * 1.0 / quantity
                            ELSE goods_total
                        END
                    ),
                    COUNT(*)
                FROM purchaseorder
                WHERE goods_title LIKE :pattern
                  AND goods_total IS NOT NULL
                  AND status NOT IN ('等待买家付款', '退款中', '交易关闭')
            """),
            {"pattern": pattern},
        ).fetchone()
        if row and row[1] and int(row[1]) > 0:
            avg_cost = row[0]
            matched = int(row[1])
            break  # use first match

    if avg_cost is not None and matched > 0:
        return ProductSKUCostSuggestResponse(
            available=True,
            suggested_cost=round(avg_cost, 2),
            matched_orders=matched,
            note=f"基于{matched}条匹配采购单的 goods_total 均值（不含运费）",
        )
    return ProductSKUCostSuggestResponse(
        available=False,
        suggested_cost=None,
        matched_orders=0,
        note="暂无匹配采购单数据",
    )


# GET /api/products/{id}/profit-summary
@router.get("/{product_id}/profit-summary", response_model=ProductProfitSummary)
def get_profit_summary(product_id: int, session: SessionDep) -> ProductProfitSummary:
    product = _get_product_or_404(product_id, session)
    rows = session.execute(
        text("""
            SELECT
                so.product_attr                                                              AS sku_id,
                COALESCE(psc.purchase_cost, 0.0)                                             AS unit_cost,
                CASE WHEN psc.purchase_cost IS NULL AND COALESCE(so.product_attr,'') != ''
                     THEN 1 ELSE 0 END                                                       AS missing_cost,
                SUM(CASE WHEN so.status = '交易成功'
                         THEN so.quantity   ELSE 0   END)                                    AS units_sold,
                SUM(CASE WHEN so.status = '交易成功'
                         THEN so.buyer_paid ELSE 0.0 END)                                    AS gross_revenue,
                SUM(CASE WHEN so.status = '交易成功'
                         THEN CAST(so.refund_amount AS REAL) ELSE 0.0 END)                   AS refund
            FROM suborder so
            LEFT JOIN productskucost psc
                ON  psc.taobao_item_id = so.taobao_item_id
                AND psc.sku_id         = COALESCE(so.product_attr, '')
            WHERE so.taobao_item_id = :item_id
            GROUP BY so.product_attr, psc.purchase_cost
        """),
        {"item_id": product.taobao_item_id},
    ).fetchall()

    units_sold = sum(int(r[3] or 0) for r in rows)
    revenue = sum((float(r[4] or 0) - float(r[5] or 0)) for r in rows)
    cost = sum(int(r[3] or 0) * float(r[1] or 0) for r in rows)
    gross_profit = revenue - cost
    gross_margin_pct = round(gross_profit / revenue * 100, 2) if revenue > 0 else None
    has_missing = any(int(r[2] or 0) for r in rows)
    weighted_avg_cost = round(cost / units_sold, 4) if units_sold > 0 else 0.0

    return ProductProfitSummary(
        taobao_item_id=product.taobao_item_id,
        units_sold=units_sold,
        revenue=round(revenue, 2),
        weighted_avg_cost=weighted_avg_cost,
        cost=round(cost, 2),
        gross_profit=round(gross_profit, 2),
        gross_margin_pct=gross_margin_pct,
        has_missing_sku_cost=has_missing,
    )


# GET /api/products/{id}/profit-monthly
@router.get("/{product_id}/profit-monthly", response_model=ProductProfitMonthlyResponse)
def get_profit_monthly(product_id: int, session: SessionDep) -> ProductProfitMonthlyResponse:
    product = _get_product_or_404(product_id, session)
    today = date.today()
    # Compute start_month: 12 calendar months back
    y = today.year
    m = today.month - 12
    while m <= 0:
        m += 12
        y -= 1
    start_month = date(y, m, 1).strftime("%Y-%m")

    rows = session.execute(
        text("""
            SELECT
                strftime('%Y-%m', COALESCE(so.paid_at, so.created_at))  AS month_key,
                so.product_attr                                          AS sku_id,
                COALESCE(psc.purchase_cost, 0.0)                         AS unit_cost,
                CASE WHEN psc.purchase_cost IS NULL AND COALESCE(so.product_attr,'') != ''
                     THEN 1 ELSE 0 END                                   AS missing_cost,
                SUM(CASE WHEN so.status = '交易成功'
                         THEN so.quantity   ELSE 0   END)                AS units_sold,
                SUM(CASE WHEN so.status = '交易成功'
                         THEN so.buyer_paid ELSE 0.0 END)                AS gross_revenue,
                SUM(CASE WHEN so.status = '交易成功'
                         THEN CAST(so.refund_amount AS REAL) ELSE 0.0 END) AS refund
            FROM suborder so
            LEFT JOIN productskucost psc
                ON  psc.taobao_item_id = so.taobao_item_id
                AND psc.sku_id         = COALESCE(so.product_attr, '')
            WHERE so.taobao_item_id = :item_id
              AND strftime('%Y-%m', COALESCE(so.paid_at, so.created_at)) >= :start_month
            GROUP BY month_key, so.product_attr, psc.purchase_cost
            ORDER BY month_key
        """),
        {"item_id": product.taobao_item_id, "start_month": start_month},
    ).fetchall()

    # Aggregate per month
    from collections import defaultdict
    month_data: dict[str, dict] = defaultdict(lambda: {
        "units_sold": 0, "revenue": 0.0, "cost": 0.0, "has_missing": False
    })
    for r in rows:
        mk = r[0]
        if not mk:
            continue
        month_data[mk]["units_sold"] += int(r[4] or 0)
        month_data[mk]["revenue"] += float(r[5] or 0) - float(r[6] or 0)
        month_data[mk]["cost"] += int(r[4] or 0) * float(r[2] or 0)
        if int(r[3] or 0):
            month_data[mk]["has_missing"] = True

    has_missing_overall = any(v["has_missing"] for v in month_data.values())
    months_present = sorted(month_data.keys())

    items = []
    for mk in months_present:
        d = month_data[mk]
        rev = d["revenue"]
        cost = d["cost"]
        gp = rev - cost
        margin = round(gp / rev * 100, 2) if rev > 0 else None
        items.append(ProductProfitMonthly(
            month=mk,
            units_sold=d["units_sold"],
            revenue=round(rev, 2),
            cost=round(cost, 2),
            gross_profit=round(gp, 2),
            gross_margin_pct=margin,
        ))

    return ProductProfitMonthlyResponse(
        months_present=months_present,
        items=items,
        has_missing_sku_cost=has_missing_overall,
    )

