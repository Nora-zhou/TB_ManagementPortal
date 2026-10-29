"""013-I01/I03：从 run 目录解析商品字段（纯函数，不联网）。

主路径：SSR HTML 内嵌的 ``window.__ICE_APP_CONTEXT__``（见 NOTES-item-page.md）。
所有字段路径都基于 2026-10-29 对真实页面的实测；改版后优先改这里。

source 语义（重要）：
- ``page_dom`` —— 真的从 HTML 里解析出了数据（SSR 属于此类）
- ``none``     —— 没有任何可用数据（未登录 / 数据未渲染 / 页面结构变了）
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import raw_store

# SSR 数据锚点：内联脚本里 var b = {...}; 然后合并进 __ICE_APP_CONTEXT__
_SSR_RE = re.compile(r"var b = (\{.*?\});for \(var k in a\)", re.S)
# 主图 URL 里的裁切参数携带原始尺寸：~crop,100,0,600,800~
_CROP_RE = re.compile(r"~crop,\d+,\d+,(\d+),(\d+)~")

CORE_FIELDS = ("title", "price_cents", "image_count", "detail_image_count")
ENHANCED_FIELDS = (
    "sales_text",
    "review_count",
    "sku_json",
    "service_json",
    "stock_total",
    "image_meta",
)


class ParseError(RuntimeError):
    """run 目录材料缺失或 manifest 损坏。"""


def _extract_context(html: str) -> dict | None:
    match = _SSR_RE.search(html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def _to_cents(money: object) -> int | None:
    """priceMoney 本身是分（如 "4990"）；带小数点的按元转分。"""
    if money is None:
        return None
    text = str(money).replace(",", "").strip()
    if not text:
        return None
    try:
        if "." in text:
            return int((Decimal(text) * 100).quantize(Decimal("1")))
        return int(text)
    except (InvalidOperation, ValueError):
        return None


def _normalize_image_url(url: object) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    if url.startswith("//"):
        return "https:" + url
    return url


def _image_meta(urls: list[str]) -> list[dict]:
    """从 URL 的 crop 参数还原尺寸；拿不到的 w/h 留 None（I02 可补下载探测）。"""
    metas: list[dict] = []
    for url in urls:
        match = _CROP_RE.search(url)
        width = int(match.group(1)) if match else None
        height = int(match.group(2)) if match else None
        metas.append(
            {
                "url": url,
                "w": width,
                "h": height,
                "ratio": round(width / height, 3) if width and height else None,
            }
        )
    return metas


def _build_skus(res: dict) -> list[dict]:
    """skuBase.skus（propPath ↔ skuId） × skuCore.sku2info（价格/库存）。"""
    props = (res.get("skuBase") or {}).get("props") or []
    name_by_vid: dict[str, str] = {}
    for prop in props:
        for value in prop.get("values") or []:
            vid = str(value.get("vid"))
            if value.get("name"):
                name_by_vid[vid] = str(value["name"])

    info_by_sku = (res.get("skuCore") or {}).get("sku2info") or {}
    skus: list[dict] = []
    for raw in (res.get("skuBase") or {}).get("skus") or []:
        sku_id = str(raw.get("skuId"))
        info = info_by_sku.get(sku_id) or {}
        prop_path = str(raw.get("propPath") or "")
        # propPath 格式："pid:vid" 或 "pid1:vid1;pid2:vid2" —— 每段取 vid 对应的值名
        parts: list[str] = []
        for pair in prop_path.split(";"):
            vid = pair.split(":", 1)[1] if ":" in pair else pair
            if name_by_vid.get(vid):
                parts.append(name_by_vid[vid])
        skus.append(
            {
                "sku_id": sku_id,
                "name": "/".join(parts) if parts else None,
                "prop_path": prop_path,
                "price_cents": _to_cents((info.get("price") or {}).get("priceMoney")),
                "stock": info.get("quantity"),
                "quantity_text": info.get("quantityText"),
                "logistics": info.get("logisticsTime"),
            }
        )
    return skus


def _reliability(result: dict) -> dict[str, int]:
    reliable: dict[str, int] = {}
    for field in CORE_FIELDS + ENHANCED_FIELDS:
        value = result.get(field)
        reliable[field] = 1 if value not in (None, "", [], {}) else 0
    return reliable


def parse_item(run_dir: Path) -> dict:
    """解析一个 run 目录，返回可落库的完整字段。

    永不抛网络异常；材料缺失时返回全 None + source="none"。
    JSON 类字段在返回值里仍是 Python 对象，序列化由 store 层负责。
    """
    manifest = raw_store.read_manifest(run_dir)
    item_id: str = manifest.get("item_id", run_dir.name)

    result: dict = {
        "run_id": manifest.get("run_id", run_dir.name),
        "item_id": item_id,
        "title": None,
        "price_cents": None,
        "promo_price_cents": None,
        "price_min_cents": None,
        "price_max_cents": None,
        "image_urls": [],
        "image_count": None,
        "image_meta": [],
        "detail_image_count": None,
        "detail_meta": None,
        "sales_text": None,
        "sales_parsed": None,
        "review_count": None,
        "rating": None,
        "review": None,
        "stock_total": None,
        "item_status": None,
        "sku_json": [],
        "service_json": None,
        "field_reliable": _reliability({}),
        "source": "none",
        "raw_path": str(run_dir),
    }

    page_html_path = run_dir / "page.html"
    if not page_html_path.exists():
        return result
    html = page_html_path.read_text(encoding="utf-8", errors="replace")

    context = _extract_context(html)
    if not context:
        return result
    try:
        res = context["loaderData"]["home"]["data"]["res"]
    except (KeyError, TypeError):
        return result

    item = res.get("item") or {}
    components = res.get("componentsVO") or {}

    # ── 标题 ──
    title = item.get("title")
    result["title"] = title.strip() if isinstance(title, str) and title.strip() else None

    # ── 主图（URL + 从 crop 参数还原的尺寸） ──
    images = [
        url
        for url in (_normalize_image_url(u) for u in (item.get("images") or []))
        if url
    ]
    result["image_urls"] = images
    result["image_count"] = len(images) if images else None
    result["image_meta"] = _image_meta(images)

    # ── 价格（分）：主价 / 券后价 / SKU 区间 ──
    price_vo = components.get("priceVO") or {}
    result["price_cents"] = _to_cents((price_vo.get("price") or {}).get("priceMoney"))
    result["promo_price_cents"] = _to_cents(
        (price_vo.get("extraPrice") or {}).get("priceMoney")
    )
    if result["price_cents"] is None:
        trade = res.get("pcTrade") or {}
        result["price_cents"] = _to_cents(
            (trade.get("pcBuyParams") or {}).get("current_price")
        )

    # ── SKU / 库存 / 价格区间 ──
    skus = _build_skus(res)
    result["sku_json"] = skus
    sku_prices = [s["price_cents"] for s in skus if s.get("price_cents") is not None]
    if sku_prices:
        result["price_min_cents"] = min(sku_prices)
        result["price_max_cents"] = max(sku_prices)
    stocks = [s["stock"] for s in skus if isinstance(s.get("stock"), int)]
    if stocks:
        result["stock_total"] = sum(stocks)
        result["item_status"] = "onsale" if result["stock_total"] > 0 else "soldout"

    # ── 月销 ──
    title_vo = components.get("titleVO") or {}
    sales_text = title_vo.get("salesDesc")
    if isinstance(sales_text, str) and sales_text.strip():
        result["sales_text"] = sales_text.strip()
    if item.get("vagueSellCount") is not None:
        result["sales_parsed"] = int(item["vagueSellCount"])
        if not result["sales_text"]:
            result["sales_text"] = f"月销 {result['sales_parsed']}"

    # ── 评价 ──
    rate_vo = components.get("rateVO") or {}
    total = rate_vo.get("totalCount")
    if total not in (None, ""):
        try:
            result["review_count"] = int(total)
        except (TypeError, ValueError):
            result["review_count"] = None
    result["review"] = {
        "count": result["review_count"],
        "favorable_rate": (rate_vo.get("favorableRate") or {}).get("rate") or None,
    }

    # ── 服务（邮费 / 发货时效 / 店铺标签） ──
    delivery_vo = components.get("deliveryVO") or {}
    store_card = components.get("storeCardVO") or {}
    result["service_json"] = {
        "freight": delivery_vo.get("freight"),
        "ship_aging": delivery_vo.get("agingDesc"),
        "delivery_from": delivery_vo.get("deliveryFromAddr"),
        "labels": [
            label.get("contentDesc")
            for label in (store_card.get("labelList") or [])
            if label.get("contentDesc")
        ],
    }

    # ── 详情图（来自 desc 内容） ──
    desc_path = run_dir / "desc.html"
    if desc_path.exists():
        desc_html = desc_path.read_text(encoding="utf-8", errors="replace")
        result["detail_image_count"] = desc_html.lower().count("<img")
        result["detail_meta"] = {
            "img_count": result["detail_image_count"],
            "fetched": True,
        }

    result["source"] = "page_dom"
    result["field_reliable"] = _reliability(result)
    return result
