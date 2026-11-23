"""013-I07：店铺层指标。

三条口径约束（都来自实际数据，不是拍脑袋）：

1. **窗口以数据最后一天为终点，不以今天为终点**。
   订单数据可能滞后（当前截止 2026-05-27），按 today 往前推会把动销率算成 0。
2. **交易关闭不计入有效销售**。当前库里 29% 的订单是关闭状态，混进去会虚增销量。
3. **动销率的分母用商品表，不用订单历史**。
   订单里出现过的商品（364）多于商品表（251），用后者会把已下架商品也算成「在售」。
   两个口径都返回，前端标明差异。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case
from sqlmodel import Session, func, select

from models import Product, SubOrder

CLOSED_STATUS = "交易关闭"

# 成交单价分档（分）
PRICE_BANDS = (
    (0, 2000, "0–20 元"),
    (2000, 5000, "20–50 元"),
    (5000, 10000, "50–100 元"),
    (10000, 20000, "100–200 元"),
    (20000, None, "200 元以上"),
)


def _window(session: Session, store: int, days: int) -> tuple[datetime, datetime]:
    latest = session.exec(
        select(func.max(SubOrder.paid_at)).where(SubOrder.store == store)
    ).one()
    end = latest or datetime.now()
    return end - timedelta(days=days), end


def _fmt(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d")


def _band_of(unit_price_cents: float) -> str:
    for low, high, label in PRICE_BANDS:
        if unit_price_cents >= low and (high is None or unit_price_cents < high):
            return label
    return PRICE_BANDS[-1][2]


def _period_sell_through(session: Session, store: int) -> dict | None:
    """同期口径的动销率：分母取最新一期流量报表里「有访客」的商品。

    为什么不用商品表：商品表只有 251 个，当期流量报表有 560 个商品，
    差 300 多个。用商品表做分母，动销率会被系统性算高，而且分子分母
    还落在不同时期（商品表 5 月建、订单窗口随数据走）。这里改成
    同集合、同期：有曝光（访客 > 0）的商品里，有多少产生了支付买家。
    """
    from inspection.models import ItemTraffic

    # 取期次最长的一期：7 天和 30 天同时存在时，动销率按 30 天算才有结构意义，
    # 一周内零成交的商品不代表它不动销。
    latest = session.exec(
        select(
            ItemTraffic.period_start, ItemTraffic.period_end, ItemTraffic.period_days
        )
        .where(ItemTraffic.store == store, ItemTraffic.period_start.is_not(None))
        .order_by(ItemTraffic.period_days.desc(), ItemTraffic.period_start.desc())
        .limit(1)
    ).first()
    if latest is None:
        return None

    rows = session.exec(
        select(ItemTraffic.visitors, ItemTraffic.pay_buyers).where(
            ItemTraffic.store == store,
            ItemTraffic.period_start == latest[0],
            ItemTraffic.period_end == latest[1],
        )
    ).all()
    if not rows:
        return None

    listed = [row for row in rows if (row[0] or 0) > 0]
    sold = [row for row in listed if (row[1] or 0) > 0]
    return {
        "period_start": latest[0].date().isoformat(),
        "period_end": latest[1].date().isoformat(),
        "period_days": latest[2],
        "active": len(sold),
        "total": len(listed),
        "zero_visitor": len(rows) - len(listed),
        "dead": len(listed) - len(sold),
        "rate": round(len(sold) / len(listed), 4) if listed else 0.0,
        "basis": "最新一期流量报表中有访客的商品",
    }


def shop_metrics(session: Session, *, days: int = 90, store: int = 1) -> dict:
    """店铺层交易结构指标。纯读，不改库。"""
    start, end = _window(session, store, days)

    rows = session.exec(
        select(
            SubOrder.taobao_item_id,
            func.max(SubOrder.product_title),
            func.sum(SubOrder.quantity),
            func.sum(SubOrder.buyer_paid),
            func.count(),
        )
        .where(
            SubOrder.store == store,
            SubOrder.paid_at >= start,
            SubOrder.paid_at <= end,
            SubOrder.status != CLOSED_STATUS,
        )
        .group_by(SubOrder.taobao_item_id)
    ).all()

    items = [
        {
            "item_id": item_id,
            "title": title,
            "units": int(units or 0),
            "revenue": round(float(revenue or 0), 2),
            "orders": int(orders or 0),
        }
        for item_id, title, units, revenue, orders in rows
    ]
    items.sort(key=lambda item: item["revenue"], reverse=True)

    revenue_total = sum(item["revenue"] for item in items)
    units_total = sum(item["units"] for item in items)
    orders_total = sum(item["orders"] for item in items)

    # ── 集中度 ──
    top10 = items[:10]
    top10_revenue = sum(item["revenue"] for item in top10)
    top10_share = top10_revenue / revenue_total if revenue_total else 0.0
    for rank, item in enumerate(items, 1):
        item["rank"] = rank
        item["revenue_share"] = (
            round(item["revenue"] / revenue_total, 4) if revenue_total else 0.0
        )

    # ── 价格带（按成交单价 = 销售额 / 销量）──
    bands = {
        label: {"label": label, "items": 0, "units": 0, "revenue": 0.0}
        for _, _, label in PRICE_BANDS
    }
    for item in items:
        unit_price = (item["revenue"] / item["units"] * 100) if item["units"] else 0
        band = bands[_band_of(unit_price)]
        band["items"] += 1
        band["units"] += item["units"]
        band["revenue"] = round(band["revenue"] + item["revenue"], 2)
    for band in bands.values():
        band["revenue_share"] = (
            round(band["revenue"] / revenue_total, 4) if revenue_total else 0.0
        )

    # ── 动销率：分母用商品表 ──
    product_ids = set(
        session.exec(select(Product.taobao_item_id).where(Product.store == store)).all()
    )
    sold_ids = {item["item_id"] for item in items}
    covered = sold_ids & product_ids
    sell_through = len(covered) / len(product_ids) if product_ids else 0.0

    # 订单里出现、但商品表没有登记的商品（已下架或未导入）
    unregistered = sold_ids - product_ids

    # ── 关闭率（窗口内）──
    window_orders, window_closed = session.exec(
        select(
            func.count(),
            func.sum(case((SubOrder.status == CLOSED_STATUS, 1), else_=0)),
        ).where(
            SubOrder.store == store,
            SubOrder.paid_at >= start,
            SubOrder.paid_at <= end,
        )
    ).one()
    window_orders = int(window_orders or 0)
    close_rate = (int(window_closed or 0) / window_orders) if window_orders else 0.0

    dead_items = int(session.exec(
        select(func.count()).select_from(Product).where(Product.store == store)
    ).one() or 0) - len(covered)

    return {
        "window": {
            "start": _fmt(start),
            "end": _fmt(end),
            "days": days,
            "note": "窗口终点取订单数据的最后一天，不是今天",
        },
        "totals": {
            "revenue": round(revenue_total, 2),
            "units": units_total,
            "orders": orders_total,
            "items_sold": len(items),
            "items_registered": len(product_ids),
            "items_unregistered": len(unregistered),
            "aov": round(revenue_total / orders_total, 2) if orders_total else 0.0,
            "close_rate": round(close_rate, 4),
        },
        "sell_through": {
            "active": len(covered),
            "total": len(product_ids),
            "rate": round(sell_through, 4),
            "dead": max(dead_items, 0),
            "basis": "订单窗口内有成交 ÷ 商品表（历史口径，分母偏小）",
        },
        # 当期口径：与订单同期、同集合，页面优先展示这个
        "sell_through_period": _period_sell_through(session, store),
        "concentration": {
            "top10_revenue": round(top10_revenue, 2),
            "top10_share": round(top10_share, 4),
            "top_items": top10[:10],
        },
        "price_bands": [bands[label] for _, _, label in PRICE_BANDS],
        "top_items": items[:20],
    }
