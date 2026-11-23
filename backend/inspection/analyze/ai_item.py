"""单品 AI 诊断：这个商品卡在哪一步，下一步该改什么。

和店铺级分析的关键区别：单品的判断依据是一条链路
（曝光 → 点击 → 详情 → 价格与信任 → 成交），而流量报表是从「访客」开始的，
也就是点击之后。所以**点击率、曝光量、关键词排名这三样数据里没有**，
不能把「访客少」直接归因为「主图不好」——主图影响的是点击率。

这里把可用证据和不可用证据都写进 prompt，并要求每条结论引用具体字段，
否则模型会输出「优化主图提升点击」这种既正确又没用的建议。
"""

from __future__ import annotations

import hashlib
import json
import re

from sqlmodel import Session, func, select

from inspection.analyze.ai import (
    _clean_messages,
    _config,
    _post_chat,
    is_configured,
)
from inspection.traffic import MIN_MEANINGFUL_VISITORS, item_traffic, list_periods

CLOSED_STATUS = "交易关闭"

_ITEM_SYSTEM_PROMPT = """你是淘宝店铺的单品运营分析师。输入是一个商品的数据：
多个时间窗口的流量表现、同期订单、以及商品页快照（标题/价格/主图数/详情图数/
销量文案/评价数/SKU/库存）。

诊断链路是：曝光 → 点击 → 详情 → 价格与信任 → 成交。
数据边界要分清：
- **没有**：曝光量、点击率、搜索词排名、竞品价格。所以绝不能说
  「访客少是因为主图不好」——主图影响点击率，而点击率没有数据。
  visitors 少只能说「曝光不足」，动作是标题/类目/推广，不是改图。
- **有**：bounce_rate（详情页跳出率）、avg_stay_seconds（平均停留时长）、
  views_per_visitor（人均浏览量 = page_views / visitors）、cart_units 与
  cart_buyers（加购件数 vs 加购人数）、order_buyers（下单买家数）、
  search_visitors（搜索引导访客数）。
  这组数反映的是**点击之后**的承接质量：跳出率高、停留短 = 详情页没接住；
  加购多而下单少 = 价格或 SKU 让人犹豫；下单多而支付少 = 运费/支付环节流失。

规则：
1. 每条结论必须引用输入里的字段和数字，不要泛泛而谈。
2. 多窗口只能比日均和比率，禁止相加或取平均。
3. 访客低于 50 时明确说样本不足，不要给转化率结论。
4. 商品快照的结构问题（主图少于 5 张、详情图为 0、标题过短、无销量无评价、
   库存为 0）可以指出，但必须说明这是结构检查，不是转化率归因。
5. 动作要区分「现在做」和「现在别做」，别做的那部分同样要具体。

只输出 JSON，结构固定：
{
  "headline": "一句话结论，不超过 40 字",
  "stage": "exposure|click|detail|price|trust|deal|unclear",
  "findings": [
    {"claim": "问题", "evidence": "数据依据", "action": "具体动作"}
  ],
  "dont_do": ["现在不要做的事"],
  "data_gaps": ["做不了判断的地方"]
}
findings 给 3 到 5 条，按优先级排序。"""


def _yuan(cents) -> float | None:
    return round(cents / 100, 2) if cents else None


def _sku_count(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return len(data) if isinstance(data, list) else None


def _item_window(session: Session, item_id: str, store: int, days: int) -> dict | None:
    result = item_traffic(session, item_id=item_id, store=store, period_days=days)
    if not result.get("available"):
        return None
    item = result["item"]
    bench = result["benchmark"]
    return {
        "days": days,
        "title": item["title"],
        "visitors": item["visitors"],
        "visitors_per_day": round(item["visitors"] / days, 1),
        "buyers": item["pay_buyers"],
        "revenue": item["pay_amount"],
        "conversion_rate": item["conversion_rate"],
        "cart_units": item["cart_units"],
        "fav_units": item["fav_units"],
        "page_views": item.get("page_views"),
        "views_per_visitor": (
            round(item["page_views"] / item["visitors"], 2)
            if item.get("page_views") and item["visitors"]
            else None
        ),
        "avg_stay_seconds": item.get("avg_stay_seconds"),
        "bounce_rate": item.get("bounce_rate"),
        "cart_buyers": item.get("cart_buyers"),
        "order_buyers": item.get("order_buyers"),
        "order_amount": item.get("order_amount"),
        "search_visitors": item.get("search_visitors"),
        "visitor_rank": f"{result['rank']['visitor_rank']}/{result['rank']['total']}",
        "rate_rank": (
            f"{result['rank']['rate_rank']}/{bench['meaningful_items']}"
            if result["rank"]["rate_rank"]
            else None
        ),
        "shop_conversion_rate": bench["conversion_rate"],
        "shop_aov": bench["aov"],
        "gap_vs_average_pp": result["gap"]["vs_average_pp"],
        "lost_buyers": result["gap"]["lost_buyers"],
        "lost_revenue": result["gap"]["lost_revenue"],
        "rule_diagnosis": result["diagnosis"],
    }


def _orders(session: Session, item_id: str, store: int, start: str, end: str) -> dict:
    from models import SubOrder

    window = (
        SubOrder.paid_at >= f"{start} 00:00:00",
        SubOrder.paid_at <= f"{end} 23:59:59",
        SubOrder.taobao_item_id == item_id,
    )
    units, revenue, orders = session.exec(
        select(
            func.sum(SubOrder.quantity),
            func.sum(SubOrder.buyer_paid),
            func.count(),
        ).where(SubOrder.store == store, *window)
    ).one()
    valid = session.exec(
        select(func.count())
        .select_from(SubOrder)
        .where(SubOrder.store == store, SubOrder.status != CLOSED_STATUS, *window)
    ).one()
    closed_count = session.exec(
        select(func.count())
        .select_from(SubOrder)
        .where(SubOrder.store == store, SubOrder.status == CLOSED_STATUS, *window)
    ).one()
    return {
        "window": f"{start} ~ {end}",
        "orders": int(orders or 0),
        "orders_valid": int(valid or 0),
        "orders_closed": int(closed_count or 0),
        "units": int(units or 0),
        "revenue": round(float(revenue or 0), 2),
    }


def _snapshot(session: Session, item_id: str, store: int) -> dict | None:
    from inspection.models import ItemSnapshot

    # item_snapshot 没有 store 字段（单店采集），只按 item_id 取最新一条
    row = session.exec(
        select(ItemSnapshot)
        .where(ItemSnapshot.item_id == item_id)
        .order_by(ItemSnapshot.collected_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return {
        "title": row.title,
        "title_length": len(row.title or ""),
        "price": _yuan(row.price_cents),
        "price_range": (
            [_yuan(row.price_min_cents), _yuan(row.price_max_cents)]
            if row.price_min_cents or row.price_max_cents
            else None
        ),
        "promo_price": _yuan(row.promo_price_cents),
        "image_count": row.image_count,
        "detail_image_count": row.detail_image_count,
        "sales_text": row.sales_text,
        "sales_parsed": row.sales_parsed,
        "review_count": row.review_count,
        "rating": row.rating,
        "sku_count": _sku_count(row.sku_json),
        "stock_total": row.stock_total,
        "item_status": row.item_status,
        "collected_at": row.collected_at.isoformat(timespec="seconds")
        if row.collected_at
        else None,
        "data_reliable": bool(row.reliable),
    }


def build_item_context(session: Session, item_id: str, store: int = 1) -> dict:
    periods = list_periods(session, store=store)
    if not periods:
        return {"available": False, "reason": "no_traffic_data", "item_id": item_id}

    days_list = sorted({p["period_days"] for p in periods}, reverse=True)
    windows = {}
    for days in days_list:
        window = _item_window(session, item_id, store, days)
        if window:
            windows[f"{days}d"] = window

    if not windows:
        return {"available": False, "reason": "item_not_found", "item_id": item_id}

    longest = max(days_list)
    longest_row = next(
        (p for p in periods if p["period_days"] == longest), periods[0]
    )

    return {
        "available": True,
        "item_id": item_id,
        "traffic": windows,
        "orders": _orders(
            session, item_id, store, longest_row["period_start"], longest_row["period_end"]
        ),
        "snapshot": _snapshot(session, item_id, store),
        "sample_threshold": MIN_MEANINGFUL_VISITORS,
        "notes": [
            "流量报表从访客开始统计，没有曝光量和点击率，不能据此判断主图好坏",
            "访客低于 sample_threshold 时转化率没有统计意义",
            "多窗口是嵌套关系，只能比日均和比率",
        ],
    }


# ── 规则回退 ──


def _fallback(context: dict) -> dict:
    windows = context["traffic"]
    key = "30d" if "30d" in windows else next(iter(windows))
    main = windows[key]
    diag = main["rule_diagnosis"]
    code = diag["code"]
    threshold = context["sample_threshold"]

    stage_map = {
        "no_traffic": "exposure",
        "low_sample": "exposure",
        "low_traffic_good_rate": "exposure",
        "high_traffic_low_rate": "detail",
        "low_both": "unclear",
        "healthy": "deal",
    }

    findings = [
        {
            "claim": diag["label"],
            "evidence": (
                f"{key} 窗口访客 {main['visitors']}、买家 {main['buyers']}、"
                f"转化率 {main['conversion_rate'] * 100:.2f}%，"
                f"全店均值 {main['shop_conversion_rate'] * 100:.2f}%"
            ),
            "action": diag["advice"],
        }
    ]

    snapshot = context.get("snapshot")
    if snapshot:
        structural = []
        if (snapshot.get("image_count") or 0) < 5:
            structural.append(f"主图只有 {snapshot.get('image_count') or 0} 张")
        if not snapshot.get("detail_image_count"):
            structural.append("详情图为 0 张")
        if (snapshot.get("title_length") or 0) < 20:
            structural.append(f"标题仅 {snapshot.get('title_length')} 字")
        if not snapshot.get("sales_parsed") and not snapshot.get("review_count"):
            structural.append("无销量/评价基础")
        if structural:
            findings.append(
                {
                    "claim": "页面结构有可改进项（结构检查，不是转化率归因）",
                    "evidence": "；".join(structural),
                    "action": "先补齐主图与详情，再谈转化；这些是必要项不充分项",
                }
            )

    if main["visitors"] < threshold:
        findings.append(
            {
                "claim": "样本不足，暂不能判定承接能力",
                "evidence": f"访客 {main['visitors']} 人，低于 {threshold} 人的判定门槛",
                "action": "先解决曝光（标题/类目/推广），等访客上来再看转化",
            }
        )

    return {
        "headline": f"{diag['label']}：{key} 窗口 {main['visitors']} 访客、"
        f"{main['conversion_rate'] * 100:.2f}% 转化",
        "stage": stage_map.get(code, "unclear"),
        "findings": findings[:4],
        "dont_do": ["在没有曝光数据的情况下改主图，无法验证效果"],
        "data_gaps": ["未配置大模型，以上为规则生成"],
    }


_CACHE: dict[str, dict] = {}


def item_insight(
    session: Session, *, item_id: str, store: int = 1, refresh: bool = False
) -> dict:
    context = build_item_context(session, item_id, store=store)
    if not context.get("available"):
        return {
            "available": False,
            "reason": context.get("reason", "no_data"),
            "item_id": item_id,
            "configured": is_configured(),
        }

    key = hashlib.sha256(
        json.dumps(context, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    if not refresh and key in _CACHE:
        return {**_CACHE[key], "cached": True}

    cfg = _config()
    insight = None
    source = "rules"
    error = None

    if is_configured():
        content = _post_chat(
            cfg,
            [
                {"role": "system", "content": _ITEM_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(context, ensure_ascii=False, indent=2),
                },
            ],
            json_mode=True,
        )
        insight = _parse_item_insight(content) if content else None
        if insight is not None:
            source = "llm"
        else:
            error = "model_call_failed"

    if insight is None:
        insight = _fallback(context)

    result = {
        "available": True,
        "configured": is_configured(),
        "source": source,
        "error": error,
        "model": cfg["model"] if source == "llm" else None,
        "item_id": item_id,
        "title": (context.get("snapshot") or {}).get("title")
        or next(iter(context["traffic"].values())).get("title"),
        "insight": insight,
        "cached": False,
    }
    _CACHE[key] = result
    return result


def _strip_fence(text: str) -> str:
    return re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()


def _parse_item_insight(content: str) -> dict | None:
    """校验模型输出。结构不合规一律判废，交给规则回退。"""
    try:
        raw = json.loads(_strip_fence(content))
    except (TypeError, ValueError):
        return None
    if not isinstance(raw, dict) or not raw.get("headline"):
        return None

    findings = [
        {
            "claim": str(item.get("claim", ""))[:200],
            "evidence": str(item.get("evidence", ""))[:300],
            "action": str(item.get("action", ""))[:300],
        }
        for item in (raw.get("findings") or [])
        if isinstance(item, dict) and item.get("claim")
    ]
    if not findings:
        return None

    return {
        "headline": str(raw["headline"])[:120],
        "stage": str(raw.get("stage") or "unclear")[:16],
        "findings": findings[:5],
        "dont_do": [str(item)[:200] for item in (raw.get("dont_do") or []) if item][:4],
        "data_gaps": [str(item)[:200] for item in (raw.get("data_gaps") or []) if item][
            :5
        ],
    }


_ITEM_CHAT_PROMPT = """你是这家淘宝店铺的单品运营分析师，正在和店主讨论一个具体商品。

输入里是这个商品的多窗口流量、同期订单、商品页快照，以及全店基准。

要点：
1. 流量报表从访客开始，没有曝光和点击率。不要说「主图不好导致没流量」，
   访客少只能说曝光不足，动作是标题/类目/推广。
2. 只依据数据回答；没有的（流量来源、竞品、成本、评价内容）直说没有。
3. 回答 3 行以内，先结论后依据，动作要具体。
4. 不要输出 JSON，不要用 Markdown 表格。
"""


def item_chat(
    session: Session, *, item_id: str, store: int = 1, messages: list[dict]
) -> dict:
    context = build_item_context(session, item_id, store=store)
    if not context.get("available"):
        return {
            "available": False,
            "reason": context.get("reason", "no_data"),
            "reply": "这个商品还没有流量数据，先在「数据导入 → 流量数据」上传报表。",
        }

    cleaned = _clean_messages(messages)
    if not cleaned or cleaned[-1]["role"] != "user":
        return {"available": False, "reason": "no_question", "reply": ""}

    cfg = _config()
    if not is_configured():
        return {
            "available": True,
            "source": "rules",
            "reply": "还没配置大模型，无法对话。在 .env 填 AI_BASE_URL / AI_API_KEY 后重启后端。",
        }

    system = _ITEM_CHAT_PROMPT + "\n\n商品数据：\n" + json.dumps(
        context, ensure_ascii=False, indent=2
    )
    content = _post_chat(
        cfg,
        [{"role": "system", "content": system}, *cleaned],
        json_mode=False,
        max_tokens=800,
    )
    if not content:
        return {
            "available": True,
            "source": "rules",
            "error": "model_call_failed",
            "reply": "模型调用失败（超时或网关异常），稍后再试。",
        }

    return {
        "available": True,
        "source": "llm",
        "model": cfg["model"],
        "reply": content.strip(),
    }
