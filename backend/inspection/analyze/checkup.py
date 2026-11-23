"""商品体检：预置文案 + 判定阈值。

为什么要有这一层，而不是全交给大模型：

1. **同样的数据必须给同样的说法**。用户今天看到「主图不足」，明天看到
   「素材质量欠佳」，会认为系统不稳定。文案是产品的一部分，应该固化。
2. **模型会漏项**。体检是清单式检查，漏掉「详情图为 0」这种事不能接受；
   规则层保证每一条都被检查到，模型只负责在这些结论之上做串联和取舍。
3. **没有模型也要能用**。这是体检的兜底，不是 AI 的附属。

文案写法：problem（问题）→ impact（影响）→ action（动作），三段都不许空。
impact 尤其不能省 —— 只说「主图不足」用户不知道要不要紧。
"""

from __future__ import annotations

import hashlib
import json
import re

from sqlmodel import Session, func, select

from inspection.traffic import MIN_MEANINGFUL_VISITORS, item_traffic, list_periods

CLOSED_STATUS = "交易关闭"

# ── 判定阈值（集中在这里，改口径只改这一处）──
THRESHOLDS = {
    "bounce_rate_bad": 0.70,       # 详情页跳出率 ≥ 70% 算差
    "bounce_rate_warn": 0.60,
    "stay_seconds_short": 10.0,    # 平均停留 < 10 秒
    "cart_per_buyer": 5.0,         # 加购件数 / 支付买家 > 5 视为犹豫
    "search_share_low": 0.20,      # 搜索引导访客占比 < 20%
    "image_min": 5,                # 主图最少 5 张
    "detail_min": 3,               # 详情图最少 3 张
    "title_min": 24,               # 标题最少 24 字
    "price_spread": 1.5,           # 最高价 / 最低价 > 1.5 视为价格带跨度大
    "promo_discount": 0.75,        # 促销价低于主价 75%（7.5 折）才算价格锚点混乱
    "close_rate_warn": 0.15,       # 订单关闭率 ≥ 15%
}

# ── 预置文案 ──
# {xxx} 占位符由 evidence 填充；文案里的数字必须来自数据，不许写死。
COPY = {
    "no_traffic": {
        "title": "零曝光",
        "severity": "bad",
        "problem": "近 {days} 天访客 0 人，商品完全没有曝光。",
        "impact": "此时改详情页、改主图都不会有任何效果——没人看得到。",
        "action": "先确认商品在线、类目正确、标题含核心词；再考虑小额推广测曝光。",
    },
    "low_traffic": {
        "title": "流量不足",
        "severity": "warn",
        "problem": "近 {days} 天访客 {visitors} 人，低于 {threshold} 人的判定门槛。",
        "impact": "样本太小，转化率没有统计意义，任何按转化率的判断都不可靠。",
        "action": "先把曝光做起来：优化标题关键词、检查类目、尝试推广；再看转化。",
    },
    "bounce_high": {
        "title": "详情页跳出率高",
        "severity": "bad",
        "problem": "详情页跳出率 {bounce}，超过 {threshold_bad}。",
        "impact": "大部分访客看一屏就离开，说明首屏没有回答「这是什么、值不值」。",
        "action": "重排详情首屏：第一屏给核心卖点与实拍，第二屏给尺寸/材质对照，第三屏再讲工艺。",
    },
    "stay_short": {
        "title": "停留时间短",
        "severity": "warn",
        "problem": "平均停留 {stay} 秒，低于 {threshold}s。",
        "impact": "停留不足说明内容没有让人产生往下看的理由。",
        "action": "在首屏之后加「对比图 / 搭配场景 / 买家秀」，用图代替长段文字。",
    },
    "cart_gap": {
        "title": "加购多但不成交",
        "severity": "bad",
        "problem": "加购 {cart_units} 件，支付买家仅 {buyers} 人，加购件数是买家的 {ratio} 倍。",
        "impact": "用户已经心动却没付款，卡点通常在价格、运费、SKU 选择或信任。",
        "action": "查三件事：价格是否高于同款、是否包邮、SKU 是否让人选不出来；可用限时券收口。",
    },
    "order_pay_gap": {
        "title": "下单未支付",
        "severity": "warn",
        "problem": "下单买家 {order_buyers} 人，支付买家 {buyers} 人，有 {gap} 人在付款环节流失。",
        "impact": "下单说明购买意愿已经成立，流失只可能发生在运费、优惠、支付方式。",
        "action": "检查运费模板与优惠叠加规则；对未付款订单做催付提醒。",
    },
    "low_rate": {
        "title": "有流量不转化",
        "severity": "bad",
        "problem": "转化率 {rate}，全店均值 {shop_rate}，只有均值的 {ratio}。",
        "impact": "流量已经到位，问题在承接；这是投入产出比最高的一类商品。",
        "action": "按 详情页 → 价格 → 评价 的顺序排查，不要先去动流量。",
    },
    "search_share_low": {
        "title": "搜索流量占比低",
        "severity": "warn",
        "problem": "搜索引导访客 {search_visitors} 人，仅占 {share}。",
        "impact": "搜索流量是唯一可持续、可复用的免费流量，占比过低说明标题词没打中。",
        "action": "补核心词与长尾词到标题，对齐类目属性；避免标题堆砌无关热词。",
    },
    "image_short": {
        "title": "主图数量不足",
        "severity": "bad",
        "problem": "主图 {image_count} 张，少于 {threshold} 张。",
        "impact": "主图决定点击率，也是转化的第一道信任；张数不足等于放弃了轮播位。",
        "action": "补到 5 张：白底主图 + 场景图 + 细节图 + 尺寸图 + 对比图。",
    },
    "detail_short": {
        "title": "详情图过少",
        "severity": "warn",
        "problem": "详情图 {detail_count} 张，少于 {threshold} 张。",
        "impact": "详情图是承接主力，图片太少会让用户带着疑问离开。",
        "action": "按「卖点 → 细节 → 尺寸 → 场景 → 售后」五段式补齐。",
    },
    "title_short": {
        "title": "标题偏短",
        "severity": "warn",
        "problem": "标题 {title_length} 字，未用满 30 字。",
        "impact": "标题字数直接决定可覆盖的搜索词数量，浪费的都是免费曝光。",
        "action": "补「材质 + 品类 + 场景 + 人群」类关键词，去掉重复词。",
    },
    "no_sales": {
        "title": "无销量无评价",
        "severity": "bad",
        "problem": "销量与评价均为空或为 0。",
        "impact": "零信任基础的商品，转化率天然低，和页面做得好不好关系不大。",
        "action": "先做基础销量与真实评价（老客召回、搭配赠品），再谈优化转化。",
    },
    "price_spread": {
        "title": "价格带跨度大",
        "severity": "warn",
        "problem": "SKU 价格从 {price_min} 到 {price_max}，跨度 {ratio} 倍。",
        "impact": "价格带过宽会让用户难以判断「我该买哪个」，抬高决策成本。",
        "action": "明确主推 SKU，其余作为对照；详情页解释价差来源（克重/工艺）。",
    },
    "promo_gap": {
        "title": "促销价与主价脱节",
        "severity": "warn",
        "problem": "主价 {price}，促销价 {promo}，折扣 {discount}。",
        "impact": "过深折扣会拉低客单价并让原价失去参考意义，也容易引发比价。",
        "action": "把促销做成限时/限量，并在详情页说明原价与优惠构成。",
    },
    "stock_zero": {
        "title": "库存为零",
        "severity": "bad",
        "problem": "库存为 0。",
        "impact": "有流量却无货可卖，等于把已经获得的曝光全部浪费。",
        "action": "补货，或临时下架避免继续消耗流量与权重。",
    },
    "close_rate_high": {
        "title": "订单关闭率高",
        "severity": "warn",
        "problem": "同期订单 {orders} 单，关闭 {closed} 单，关闭率 {rate}。",
        "impact": "关闭订单会拉低店铺体验分，且多数发生在付款或发货环节。",
        "action": "核对库存准确性与发货时效，检查运费与优惠说明是否有歧义。",
    },
}

# 达标项文案：体检不能只报问题，否则用户不知道哪些已经做对了
PASS_COPY = {
    "image_ok": {
        "title": "主图数量达标",
        "problem": "主图 {image_count} 张。",
        "impact": "满足轮播位展示要求。",
        "action": "保持，后续可做 A/B 测试替换首图。",
    },
    "detail_ok": {
        "title": "详情图数量达标",
        "problem": "详情图 {detail_count} 张。",
        "impact": "具备完整的承接素材基础。",
        "action": "保持，重点看跳出率与停留是否改善。",
    },
    "traffic_ok": {
        "title": "流量规模达标",
        "problem": "近 {days} 天访客 {visitors} 人。",
        "impact": "样本量足够，转化率结论可信。",
        "action": "保持，把优化重点放在转化侧。",
    },
}


def _yuan(cents) -> str:
    return f"¥{cents / 100:.2f}" if cents else "—"


def _pct(value) -> str:
    return f"{value * 100:.2f}%" if value is not None else "—"


def _item(session: Session, item_id: str, store: int):
    """取最长一期的单品表现 + 最新快照。"""
    periods = list_periods(session, store=store)
    if not periods:
        return None, None
    longest = max(p["period_days"] for p in periods)
    traffic = item_traffic(session, item_id=item_id, store=store, period_days=longest)

    from inspection.models import ItemSnapshot

    snapshot = session.exec(
        select(ItemSnapshot)
        .where(ItemSnapshot.item_id == item_id)
        .order_by(ItemSnapshot.collected_at.desc())
        .limit(1)
    ).first()
    return traffic, snapshot


def _orders(session: Session, item_id: str, store: int, start: str, end: str) -> dict:
    from models import SubOrder

    window = (
        SubOrder.paid_at >= f"{start} 00:00:00",
        SubOrder.paid_at <= f"{end} 23:59:59",
        SubOrder.taobao_item_id == item_id,
    )
    total = session.exec(
        select(func.count()).select_from(SubOrder).where(SubOrder.store == store, *window)
    ).one()
    closed = session.exec(
        select(func.count())
        .select_from(SubOrder)
        .where(SubOrder.store == store, SubOrder.status == CLOSED_STATUS, *window)
    ).one()
    return {"orders": int(total or 0), "closed": int(closed or 0)}


def _rule_checkup(session: Session, *, item_id: str, store: int = 1) -> dict:
    """规则层：把每一项都检查一遍，产出候选信号。

    注意它只负责「有没有这个信号」，不负责最终判断——判断交给 _ai_judge，
    因为它不知道样本量、两期差异、商品是不是刚上架。
    """
    traffic, snapshot = _item(session, item_id, store)
    if not traffic or not traffic.get("available"):
        return {
            "available": False,
            "item_id": item_id,
            "reason": (traffic or {}).get("reason", "no_traffic_data"),
        }

    item = traffic["item"]
    bench = traffic["benchmark"]
    days = traffic["period_days"]
    visitors = item["visitors"]
    buyers = item["pay_buyers"]
    rate = item["conversion_rate"]
    shop_rate = bench["conversion_rate"]

    snap: dict = {}
    if snapshot is not None:
        snap = {
            field: getattr(snapshot, field, None)
            for field in (
                "title",
                "price_cents",
                "promo_price_cents",
                "price_min_cents",
                "price_max_cents",
                "image_count",
                "detail_image_count",
                "sales_parsed",
                "review_count",
                "stock_total",
            )
        }

    problems: list[dict] = []
    passes: list[dict] = []

    def add(code: str, severity: str, evidence: str, **fmt):
        copy = COPY[code]
        problems.append(
            {
                "code": code,
                "title": copy["title"],
                "severity": severity,
                "problem": copy["problem"].format(**fmt),
                "impact": copy["impact"],
                "action": copy["action"],
                "evidence": evidence,
            }
        )

    def ok(code: str, evidence: str, **fmt):
        copy = PASS_COPY[code]
        passes.append(
            {
                "code": code,
                "title": copy["title"],
                "severity": "ok",
                "problem": copy["problem"].format(**fmt),
                "impact": copy["impact"],
                "action": copy["action"],
                "evidence": evidence,
            }
        )

    # ── 流量层 ──
    if visitors == 0:
        add("no_traffic", "bad", f"{days} 天访客 0", days=days)
    elif visitors < MIN_MEANINGFUL_VISITORS:
        add(
            "low_traffic",
            "warn",
            f"{days} 天访客 {visitors}",
            days=days,
            visitors=visitors,
            threshold=MIN_MEANINGFUL_VISITORS,
        )
    else:
        ok("traffic_ok", f"{days} 天访客 {visitors}", days=days, visitors=visitors)

    search_visitors = item.get("search_visitors")
    if visitors and search_visitors is not None:
        share = search_visitors / visitors
        if share < THRESHOLDS["search_share_low"]:
            add(
                "search_share_low",
                "warn",
                f"搜索访客 {search_visitors}/{visitors} = {share * 100:.1f}%",
                search_visitors=search_visitors,
                share=f"{share * 100:.1f}%",
            )

    # ── 承接层 ──
    bounce = item.get("bounce_rate")
    if bounce is not None:
        if bounce >= THRESHOLDS["bounce_rate_bad"]:
            add(
                "bounce_high",
                "bad",
                f"跳出率 {bounce * 100:.2f}%",
                bounce=_pct(bounce),
                threshold_bad=_pct(THRESHOLDS["bounce_rate_bad"]),
            )
        elif bounce >= THRESHOLDS["bounce_rate_warn"]:
            add(
                "bounce_high",
                "warn",
                f"跳出率 {bounce * 100:.2f}%",
                bounce=_pct(bounce),
                threshold_bad=_pct(THRESHOLDS["bounce_rate_bad"]),
            )

    stay = item.get("avg_stay_seconds")
    if stay is not None and stay < THRESHOLDS["stay_seconds_short"]:
        add(
            "stay_short",
            "warn",
            f"平均停留 {stay}s",
            stay=f"{stay:.1f}",
            threshold=f"{THRESHOLDS['stay_seconds_short']:.0f}",
        )

    # ── 行为层 ──
    cart_units = item.get("cart_units")
    if cart_units and buyers and cart_units / buyers >= THRESHOLDS["cart_per_buyer"]:
        add(
            "cart_gap",
            "bad",
            f"加购 {cart_units} 件 / 买家 {buyers} 人",
            cart_units=cart_units,
            buyers=buyers,
            ratio=f"{cart_units / buyers:.1f}",
        )

    order_buyers = item.get("order_buyers")
    if order_buyers and buyers and order_buyers > buyers:
        add(
            "order_pay_gap",
            "warn",
            f"下单 {order_buyers} / 支付 {buyers}",
            order_buyers=order_buyers,
            buyers=buyers,
            gap=order_buyers - buyers,
        )

    if visitors >= MIN_MEANINGFUL_VISITORS and shop_rate and rate < shop_rate * 0.6:
        add(
            "low_rate",
            "bad",
            f"转化 {rate * 100:.2f}% vs 全店 {shop_rate * 100:.2f}%",
            rate=_pct(rate),
            shop_rate=_pct(shop_rate),
            ratio=f"{rate / shop_rate * 100:.0f}%",
        )

    # ── 结构层（快照） ──
    image_count = snap.get("image_count")
    if image_count is not None:
        if image_count < THRESHOLDS["image_min"]:
            add(
                "image_short",
                "bad",
                f"主图 {image_count} 张",
                image_count=image_count,
                threshold=THRESHOLDS["image_min"],
            )
        else:
            ok("image_ok", f"主图 {image_count} 张", image_count=image_count)

    detail_count = snap.get("detail_image_count")
    if detail_count is not None:
        if detail_count < THRESHOLDS["detail_min"]:
            add(
                "detail_short",
                "warn",
                f"详情图 {detail_count} 张",
                detail_count=detail_count,
                threshold=THRESHOLDS["detail_min"],
            )
        else:
            ok("detail_ok", f"详情图 {detail_count} 张", detail_count=detail_count)

    title = snap.get("title") or item.get("title") or ""
    if title and len(title) < THRESHOLDS["title_min"]:
        add(
            "title_short",
            "warn",
            f"标题 {len(title)} 字",
            title_length=len(title),
        )

    if snap.get("stock_total") == 0:
        add("stock_zero", "bad", "库存 0")

    if snap and not snap.get("sales_parsed") and not snap.get("review_count"):
        add("no_sales", "bad", "销量/评价均为空")

    price_min = snap.get("price_min_cents")
    price_max = snap.get("price_max_cents")
    if price_min and price_max and price_min > 0:
        spread = price_max / price_min
        if spread > THRESHOLDS["price_spread"]:
            add(
                "price_spread",
                "warn",
                f"{_yuan(price_min)} ~ {_yuan(price_max)}",
                price_min=_yuan(price_min),
                price_max=_yuan(price_max),
                ratio=f"{spread:.1f}",
            )

    price = snap.get("price_cents")
    promo = snap.get("promo_price_cents")
    if price and promo and promo < price * THRESHOLDS["promo_discount"]:
        add(
            "promo_gap",
            "warn",
            f"主价 {_yuan(price)} / 促销 {_yuan(promo)}",
            price=_yuan(price),
            promo=_yuan(promo),
            discount=f"{promo / price * 10:.1f} 折",
        )

    # ── 订单层 ──
    periods = list_periods(session, store=store)
    longest_row = max(periods, key=lambda p: p["period_days"])
    orders = _orders(session, item_id, store, longest_row["period_start"], longest_row["period_end"])
    if orders["orders"] >= 5:
        close_rate = orders["closed"] / orders["orders"]
        if close_rate >= THRESHOLDS["close_rate_warn"]:
            add(
                "close_rate_high",
                "warn",
                f"{orders['closed']}/{orders['orders']} 关闭",
                orders=orders["orders"],
                closed=orders["closed"],
                rate=f"{close_rate * 100:.1f}%",
            )

    order = {"bad": 0, "warn": 1, "ok": 2}
    problems.sort(key=lambda row: order.get(row["severity"], 3))
    items = problems + passes

    bad = sum(1 for row in problems if row["severity"] == "bad")
    warn = sum(1 for row in problems if row["severity"] == "warn")
    if bad:
        verdict = f"{bad} 项必须改" + (f"，{warn} 项建议改" if warn else "")
    elif warn:
        verdict = f"无硬伤，{warn} 项可优化"
    else:
        verdict = "结构无硬伤"

    return {
        "available": True,
        "item_id": item_id,
        "title": title or None,
        "period_days": days,
        "snapshot_available": bool(snap),
        "summary": {
            "bad": bad,
            "warn": warn,
            "ok": len(passes),
            "verdict": verdict,
        },
        "items": items,
        # 原始指标一并返回：AI 判定时要用它判断「这个信号成不成立」，
        # 比如访客只有 26 人时，转化率低这条信号应该被判为不成立。
        "metrics": {
            "period_days": days,
            "visitors": visitors,
            "buyers": buyers,
            "conversion_rate": rate,
            "shop_conversion_rate": shop_rate,
            "sample_threshold": MIN_MEANINGFUL_VISITORS,
            "bounce_rate": item.get("bounce_rate"),
            "avg_stay_seconds": item.get("avg_stay_seconds"),
            "views_per_visitor": (
                round(item["page_views"] / visitors, 2)
                if item.get("page_views") and visitors
                else None
            ),
            "cart_units": item.get("cart_units"),
            "order_buyers": item.get("order_buyers"),
            "search_visitors": item.get("search_visitors"),
            "image_count": snap.get("image_count"),
            "detail_image_count": snap.get("detail_image_count"),
            "title_length": len(title) if title else None,
            "price": _yuan(snap.get("price_cents")),
            "promo_price": _yuan(snap.get("promo_price_cents")),
            "price_min": _yuan(snap.get("price_min_cents")),
            "price_max": _yuan(snap.get("price_max_cents")),
            "stock_total": snap.get("stock_total"),
            "sales_parsed": snap.get("sales_parsed"),
            "review_count": snap.get("review_count"),
            "orders": orders["orders"],
            "orders_closed": orders["closed"],
        },
    }


# ── 判定层：规则只报信号，成不成立由这一层定 ──

_JUDGE_SYSTEM_PROMPT = """你是淘宝店铺运营审核员。规则层已经把商品逐项查过一遍，
给你的是**候选信号**，不是最终结论。你要逐条判断这个信号成不成立。

规则层看不到的三件事，必须由你补上：
1. **样本量**。访客数低于 metrics.sample_threshold 时，转化率、跳出率、停留时长、
   加购比例都只是噪声。相关信号判为不成立（keep=false），reason 里写明
   「访客只有 N 人，低于 M 人的判定门槛」。
2. **对比口径**。输入只有一期数据，没有环比。绝不能说「变差/下滑/趋势」，
   没有第二期就没有趋势这回事。
3. **商品阶段**。无销量无评价的商品，转化率天然低，这属于信任基础不足，
   不是页面问题；刚上架的商品不要要求它已经转化。

判定要求：
- 只使用输入里出现过的数字，不要编造行业均值、竞品、历史数据。
- 只判定 severity 为 bad / warn 的 signals。severity 为 ok 的条目是已经达标的事实，
  不要输出它们的 judgement。
- 每条 judgement 都要给 reason，且 reason 里必须有具体数字。
- **降级要克制**。没有环比只影响「变好/变差」这类趋势判断，不能拿来当降级的理由；
  只有这两种情况才把 bad 降为 warn：数字只是略微越过阈值（例如跳出率 70%~75%），
  或该比率的分母小于 5（买家只有 2、3 人时比率不稳）。证据成立就保持原 severity。
- 只有明确不成立才 keep=false，比如指标本身没有统计意义、或数字与结论方向相反。
- 结构项（主图数、详情图数、标题长度、库存、价格带、促销价）是客观事实，
  不因样本量小而删除。
- 必须覆盖每一个 bad / warn 的 code，不要新增 code。
- severity 只能给 bad 或 warn。

只输出 JSON，结构固定：
{
  "judgements": [
    {"code": "信号 code", "keep": true, "severity": "bad|warn", "reason": "依据，含具体数字"}
  ],
  "verdict": "一句话总结，不超过 40 字",
  "data_gaps": ["哪些判断因为数据不足做不了"]
}"""

# 需要足够样本量才成立的信号：访客太少时它们只是噪声
_SAMPLE_SENSITIVE = ("low_rate", "cart_gap", "order_pay_gap", "search_share_low")
# 可降级不可删除的结构项
_STRUCTURE_CODES = (
    "image_short",
    "detail_short",
    "title_short",
    "stock_zero",
    "price_spread",
    "promo_gap",
)

_JUDGE_CACHE: dict[str, dict] = {}


def _judge_payload(result: dict) -> dict:
    """给模型的最小输入：原始指标 + 候选信号，不含明细表。"""
    return {
        "title": result.get("title"),
        "window_days": result["period_days"],
        "metrics": result["metrics"],
        "signals": [
            {
                "code": row["code"],
                "severity": row["severity"],
                "problem": row["problem"],
                "evidence": row["evidence"],
            }
            for row in result["items"]
        ],
        "notes": [
            "metrics.sample_threshold 是最小有意义访客数，访客低于它就是样本不足",
            "只有这一期数据，没有环比，不要描述趋势",
        ],
    }


def _parse_judge(content: str) -> dict | None:
    """校验模型输出。结构不合规一律判废，交给规则回退。"""
    cleaned = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        raw = json.loads(cleaned)
    except (TypeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None

    judgements = []
    for row in raw.get("judgements") or []:
        if not isinstance(row, dict) or not row.get("code"):
            continue
        severity = str(row.get("severity") or "").lower()
        judgements.append(
            {
                "code": str(row["code"]),
                "keep": bool(row.get("keep", True)),
                "severity": severity if severity in {"bad", "warn"} else None,
                "reason": str(row.get("reason") or "")[:300],
            }
        )
    if not judgements:
        return None

    return {
        "judgements": judgements,
        "verdict": str(raw.get("verdict") or "")[:120] or None,
        "data_gaps": [str(item)[:200] for item in (raw.get("data_gaps") or []) if item][:5],
    }


def _fallback_judge(result: dict) -> dict:
    """没模型时的判定：只做一件确定的事——样本不足就撤掉噪声信号。

    这条逻辑本来就写在规则里（转化率那条已经卡了门槛），这里把它推广到
    跳出率、停留、加购、搜索占比，避免小样本商品被报一堆假问题。
    """
    metrics = result["metrics"]
    visitors = metrics.get("visitors") or 0
    threshold = metrics.get("sample_threshold") or MIN_MEANINGFUL_VISITORS
    judgements: list[dict] = []
    gaps: list[str] = []

    if visitors < threshold:
        for row in result["items"]:
            code = row["code"]
            if code in _SAMPLE_SENSITIVE:
                judgements.append(
                    {
                        "code": code,
                        "keep": False,
                        "severity": None,
                        "reason": (
                            f"访客只有 {visitors} 人，低于 {threshold} 人的判定门槛，"
                            "这个信号没有统计意义"
                        ),
                    }
                )
            elif code in {"bounce_high", "stay_short"} and row["severity"] == "bad":
                judgements.append(
                    {
                        "code": code,
                        "keep": True,
                        "severity": "warn",
                        "reason": (
                            f"访客只有 {visitors} 人，跳出率与停留时长的波动大，先降级观察"
                        ),
                    }
                )
        gaps.append(f"访客 {visitors} 人，低于 {threshold} 人，转化类结论不可用")

    return {"judgements": judgements, "verdict": None, "data_gaps": gaps}


def _apply_judgement(result: dict, judgement: dict) -> dict:
    """把判定结果合并回规则结果：撤销不成立的信号，调整严重程度，重算汇总。"""
    decisions = {row["code"]: row for row in judgement.get("judgements", [])}
    kept: list[dict] = []
    dismissed: list[dict] = []

    for row in result["items"]:
        # 已达标项是客观事实，不需要模型裁决，也不接受改写
        decision = None if row["severity"] == "ok" else decisions.get(row["code"])
        if decision is None or decision.get("keep", True):
            merged = dict(row)
            if decision:
                if decision.get("severity"):
                    merged["severity"] = decision["severity"]
                if decision.get("reason"):
                    merged["reason"] = decision["reason"]
            kept.append(merged)
        else:
            dismissed.append(
                {**row, "reason": decision.get("reason") or "判定为信号不成立"}
            )

    order = {"bad": 0, "warn": 1, "ok": 2}
    kept.sort(key=lambda row: order.get(row["severity"], 3))

    bad = sum(1 for row in kept if row["severity"] == "bad")
    warn = sum(1 for row in kept if row["severity"] == "warn")
    if bad:
        verdict = f"{bad} 项必须改" + (f"，{warn} 项建议改" if warn else "")
    elif warn:
        verdict = f"无硬伤，{warn} 项可优化"
    else:
        verdict = "结构无硬伤"

    return {
        "items": kept,
        "dismissed": dismissed,
        "summary": {
            "bad": bad,
            "warn": warn,
            "ok": sum(1 for row in kept if row["severity"] == "ok"),
            "verdict": judgement.get("verdict") or verdict,
        },
    }


def _ai_judge(payload: dict) -> dict | None:
    """判定层：让模型逐条裁决候选信号，返回 judgement；不可用就返回 None。"""
    from inspection.analyze.ai import _config, _post_chat, is_configured

    if not is_configured():
        return None
    content = _post_chat(
        _config(),
        [
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
        ],
        json_mode=True,
        max_tokens=900,
    )
    return _parse_judge(content) if content else None


def item_checkup(
    session: Session, *, item_id: str, store: int = 1, refresh: bool = False
) -> dict:
    """商品体检入口：规则层出候选信号，判定层裁决，再合并成一份结论。

    未配置模型 / 调用失败 / 输出不合规时，退回规则判定（source=rules），
    结论结构不变，前端不需要区分两种模式。
    """
    from inspection.analyze.ai import _config, is_configured

    result = _rule_checkup(session, item_id=item_id, store=store)
    if not result.get("available") or not result.get("items"):
        return {**result, "source": "rules", "configured": is_configured()}

    payload = _judge_payload(result)
    key = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    if not refresh and key in _JUDGE_CACHE:
        return {**_JUDGE_CACHE[key], "cached": True}

    configured = is_configured()
    judgement = _ai_judge(payload)
    source = "llm" if judgement is not None else "rules"
    error = None
    if judgement is None:
        error = "model_call_failed" if configured else None
        judgement = _fallback_judge(result)

    merged = _apply_judgement(result, judgement)
    out = {
        **result,
        "items": merged["items"],
        "dismissed": merged["dismissed"],
        "summary": merged["summary"],
        "source": source,
        "configured": configured,
        "error": error,
        "model": _config()["model"] if source == "llm" else None,
        "data_gaps": judgement.get("data_gaps") or [],
        "cached": False,
    }
    _JUDGE_CACHE[key] = out
    return out
