"""AI 解读：把 7 天 / 30 天两期流量结构交给大模型，产出可执行的结论。

三条约束（不遵守就会得到正确的废话）：

1. **不喂原始表，只喂已经算好的指标**。560 行商品明细塞进 prompt，模型会
   开始编造具体商品，而且成本随商品数线性上涨。这里只给聚合数字 + 偏离量。
2. **两期是嵌套关系**（7 天落在 30 天里），所以只能比「日均」，不能相加、
   不能取平均。这一点必须写死在 prompt 里，否则模型会把两个数加起来。
3. **没有 API Key 也要能出结论**。未配置 / 调用失败 / 输出不合法时，退回到
   纯规则生成的同结构结果，前端不需要区分两种模式。

配置写在项目根目录 .env（键名见 _CONFIG_KEYS），不落库、不返回给前端。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from sqlalchemy import case
from sqlmodel import Session, func, select

from inspection.traffic import list_periods, traffic_analysis

# 项目根目录 = backend/ 的上一级（.env 位于根目录）
_BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(_BASE_DIR / ".env")

CLOSED_STATUS = "交易关闭"

_SYSTEM_PROMPT = """你是淘宝店铺的运营分析师。用户会给你同一家店两个时间窗口的流量结构指标。

规则（必须遵守，违反即视为错误）：
1. 短窗口完全落在长窗口内部，两者是嵌套关系。只能比较「日均」和「比率」，
   绝对不允许把两个窗口的数值相加、取平均或做加权。
2. 只使用输入里出现过的数字。不要编造商品名、竞品、行业均值、历史趋势。
3. 这个店绝大多数商品零成交。不要用「转化率排名」下结论，要结合访客分档、
   零成交占比、访客集中度一起看。
4. 样本不足时明确说样本不足：有访客但访客很少的档位，转化率没有统计意义；
   7 天窗口里单个商品的转化率波动很大，不要据此判定单个商品好坏。
5. 口径提示：订单侧「交易关闭」不计入成交；流量侧的支付金额包含下单后关闭的订单，
   两个口径的金额本来就不相等，不要当成数据错误。
6. 引用具体商品时，必须带上它所属的窗口，并写成「近 7 天」「近 30 天」
   这样的自然说法。不要照抄 window_days 这类字段名，也不要写成
   「（window_days:7）」这种机器格式。把长窗口的数字说成「近几天」是错误。
7. 结论要能落到动作上：改页面、调价格、调推广、还是先补数据。

输出格式：只输出 JSON，不要 Markdown、不要解释。结构固定为：
{
  "headline": "一句话结论，不超过 40 字",
  "findings": [
    {"claim": "判断", "evidence": "支撑判断的具体数字", "action": "具体动作"}
  ],
  "data_gaps": ["哪些判断因为数据不足做不了"]
}
findings 给 3 到 5 条，按重要性排序。"""


def _verify_option():
    """内网网关常见自签证书：优先用指定的 CA 文件，其次才允许整体关闭校验。"""
    ca_bundle = (os.getenv("AI_CA_BUNDLE") or "").strip()
    if ca_bundle:
        return ca_bundle
    raw = (os.getenv("AI_VERIFY_SSL") or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _config() -> dict:
    return {
        "base_url": (os.getenv("AI_BASE_URL") or "").strip().rstrip("/"),
        "api_key": (os.getenv("AI_API_KEY") or "").strip(),
        "model": (os.getenv("AI_MODEL") or "deepseek-chat").strip(),
        "timeout": float(os.getenv("AI_TIMEOUT") or 60),
        "max_tokens": int(os.getenv("AI_MAX_TOKENS") or 1200),
        "verify": _verify_option(),
    }


def is_configured() -> bool:
    cfg = _config()
    return bool(cfg["base_url"] and cfg["api_key"])


def status() -> dict:
    cfg = _config()
    return {
        "configured": is_configured(),
        "model": cfg["model"] if is_configured() else None,
    }


def _pct_change(current: float, base: float) -> float | None:
    if not base:
        return None
    return round((current - base) / base, 4)


def _period_summary(session: Session, store: int, row: dict) -> dict | None:
    start = date.fromisoformat(row["period_start"])
    end = date.fromisoformat(row["period_end"])
    result = traffic_analysis(
        session, store=store, period_start=start, period_end=end
    )
    if result.get("empty"):
        return None

    totals = result["totals"]
    dist = result["distribution"]
    conc = result["concentration"]
    days = result["period_days"] or 1
    items = result["item_count"]

    return {
        "period_start": row["period_start"],
        "period_end": row["period_end"],
        "days": days,
        "items": items,
        "visitors": totals["visitors"],
        "visitors_per_day": round(totals["visitors"] / days, 1),
        "buyers": totals["buyers"],
        "conversion_rate": totals["conversion_rate"],
        "revenue": totals["revenue"],
        "revenue_per_day": round(totals["revenue"] / days, 2),
        "aov": totals["aov"],
        "zero_order_items": dist["zero_order"],
        "zero_order_share": round(dist["zero_order"] / items, 4) if items else None,
        "zero_visitor_items": dist["zero_visitor"],
        "meaningful_items": dist["meaningful_items"],
        "visitor_p50": dist["visitor_p50"],
        "visitor_p90": dist["visitor_p90"],
        "top10_visitor_share": conc["top10_share"],
        "bands": [
            {
                "label": band["label"],
                "items": band["items"],
                "visitors": band["visitors"],
                "conversion_rate": band["conversion_rate"],
            }
            for band in result["bands"]
        ],
        "high_traffic_low_rate": [
            {
                "title": item["title"],
                "window_days": days,
                "visitors": item["visitors"],
                "conversion_rate": item["conversion_rate"],
                "lost_revenue": item["lost_revenue"],
                "aov_basis": item["aov_basis"],
            }
            for item in result["suspects"][:5]
        ],
    }


def _order_summary(session: Session, store: int, start: str, end: str) -> dict:
    """订单侧同期摘要，用于和流量侧交叉验证。"""
    from models import SubOrder

    window = (
        SubOrder.paid_at >= f"{start} 00:00:00",
        SubOrder.paid_at <= f"{end} 23:59:59",
    )
    revenue, orders, closed = session.exec(
        select(
            func.sum(SubOrder.buyer_paid),
            func.count(),
            func.sum(case((SubOrder.status == CLOSED_STATUS, 1), else_=0)),
        ).where(SubOrder.store == store, *window)
    ).one()
    valid = session.exec(
        select(func.count())
        .select_from(SubOrder)
        .where(SubOrder.store == store, SubOrder.status != CLOSED_STATUS, *window)
    ).one()
    return {
        "orders": int(orders or 0),
        "orders_valid": int(valid or 0),
        "orders_closed": int(closed or 0),
        "revenue_all": round(float(revenue or 0), 2),
    }


def build_context(session: Session, store: int) -> dict:
    """构造给模型的输入：两期摘要 + 日均偏离 + 订单侧对账。"""
    periods = list_periods(session, store=store)
    if not periods:
        return {"available": False, "reason": "no_traffic_data"}

    # 基线取「期次最长」的一期，近期取「期次最短」的最近一期
    baseline_row = max(periods, key=lambda p: (p["period_days"], p["period_start"]))
    min_days = min(p["period_days"] for p in periods)
    recent_row = max(
        (p for p in periods if p["period_days"] == min_days),
        key=lambda p: p["period_start"],
    )

    baseline = _period_summary(session, store, baseline_row)
    recent = None
    if recent_row != baseline_row:
        recent = _period_summary(session, store, recent_row)

    if baseline is None:
        return {"available": False, "reason": "no_traffic_data"}

    delta = None
    if recent:
        delta = {
            "visitors_per_day": _pct_change(
                recent["visitors_per_day"], baseline["visitors_per_day"]
            ),
            "conversion_rate_pp": round(
                (recent["conversion_rate"] - baseline["conversion_rate"]) * 100, 2
            ),
            "aov": _pct_change(recent["aov"], baseline["aov"]),
            "zero_order_share_pp": round(
                ((recent["zero_order_share"] or 0) - (baseline["zero_order_share"] or 0))
                * 100,
                2,
            ),
            "top10_visitor_share_pp": round(
                (recent["top10_visitor_share"] - baseline["top10_visitor_share"]) * 100, 2
            ),
        }

    return {
        "available": True,
        "baseline": baseline,
        "recent": recent,
        "delta": delta,
        "orders": _order_summary(
            session, store, baseline["period_start"], baseline["period_end"]
        ),
        "notes": [
            "recent 完全包含在 baseline 内，两者只能比日均与比率，不能相加或平均",
            "订单侧不含交易关闭；流量侧支付金额含下单后关闭的订单，金额不相等属正常",
            "baseline.high_traffic_low_rate 里的数字属于 baseline 窗口，"
            "不要描述成近几天的情况；每项都带 window_days 字段",
        ],
    }


# ── 规则回退：没有模型时也要给出同结构的结论 ──


def _fallback(context: dict) -> dict:
    base = context["baseline"]
    recent = context.get("recent")
    delta = context.get("delta") or {}
    findings = []

    if recent and delta:
        visitor_change = delta.get("visitors_per_day")
        cr_change = delta.get("conversion_rate_pp")
        if visitor_change is not None:
            direction = "上升" if visitor_change > 0 else "下降"
            findings.append(
                {
                    "claim": f"近 {recent['days']} 天日均访客{direction} {abs(visitor_change) * 100:.0f}%",
                    "evidence": (
                        f"日均 {base['visitors_per_day']} → {recent['visitors_per_day']}，"
                        f"转化率 {base['conversion_rate'] * 100:.2f}% → "
                        f"{recent['conversion_rate'] * 100:.2f}%（{cr_change:+.2f}pp）"
                    ),
                    "action": (
                        "流量涨而转化没涨，先查承接：主图、价格锚点、详情页首屏"
                        if (visitor_change > 0 and (cr_change or 0) <= 0)
                        else "维持当前投放节奏，继续观察转化是否同步变化"
                    ),
                }
            )

    zero_share = base.get("zero_order_share")
    if zero_share is not None:
        findings.append(
            {
                "claim": f"零成交商品占 {zero_share * 100:.0f}%，结构问题大于单点问题",
                "evidence": (
                    f"{base['items']} 个商品中 {base['zero_order_items']} 个零成交；"
                    f"访客中位数 {base['visitor_p50']}，访客 ≥50 的仅 "
                    f"{base['meaningful_items']} 个"
                ),
                "action": "先解决曝光（标题/类目/推广），再谈转化；按转化率排序没有意义",
            }
        )

    findings.append(
        {
            "claim": f"流量集中在头部，前 10 个商品拿走 {base['top10_visitor_share'] * 100:.0f}% 访客",
            "evidence": (
                f"全店 {base['visitors']} 访客、{base['buyers']} 买家，"
                f"客单价 ¥{base['aov']}"
            ),
            "action": "头部商品优先补承接（详情页/评价），长尾靠调整类目与推广获取曝光",
        }
    )

    return {
        "headline": (
            f"{base['days']} 天窗口：{base['visitors']} 访客 / {base['buyers']} 买家 / "
            f"{base['conversion_rate'] * 100:.2f}% 转化"
        ),
        "findings": findings[:4],
        "data_gaps": ["未配置大模型，以上为规则生成，没有语义归纳"],
    }


# ── 模型调用 ──


def _extract_json(text: str) -> dict | None:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict) or not data.get("headline"):
        return None
    findings = [
        item
        for item in (data.get("findings") or [])
        if isinstance(item, dict) and item.get("claim")
    ]
    if not findings:
        return None
    gaps = [str(item) for item in (data.get("data_gaps") or []) if item]
    return {
        "headline": str(data["headline"])[:120],
        "findings": [
            {
                "claim": str(item.get("claim", ""))[:200],
                "evidence": str(item.get("evidence", ""))[:300],
                "action": str(item.get("action", ""))[:300],
            }
            for item in findings[:6]
        ],
        "data_gaps": gaps[:5],
    }


def _post_chat(
    cfg: dict, messages: list[dict], *, json_mode: bool, max_tokens: int | None = None
) -> str | None:
    """统一出口：结构化解读和自由对话都走这里，只是 json_mode 不同。"""
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.2 if json_mode else 0.4,
        "max_tokens": max_tokens or cfg["max_tokens"],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        with httpx.Client(timeout=cfg["timeout"], verify=cfg["verify"]) as client:
            response = client.post(
                f"{cfg['base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        return None


def _call_model(cfg: dict, context: dict) -> dict | None:
    content = _post_chat(
        cfg,
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False, indent=2),
            },
        ],
        json_mode=True,
    )
    return _extract_json(content) if content else None


# ── 缓存：同一份数据不重复烧钱 ──

_CACHE: dict[str, dict] = {}


def generate(session: Session, *, store: int = 1, refresh: bool = False) -> dict:
    context = build_context(session, store=store)
    if not context.get("available"):
        return {
            "available": False,
            "reason": context.get("reason", "no_data"),
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
        insight = _call_model(cfg, context)
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
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window": {
            "baseline": {
                "start": context["baseline"]["period_start"],
                "end": context["baseline"]["period_end"],
                "days": context["baseline"]["days"],
            },
            "recent": (
                {
                    "start": context["recent"]["period_start"],
                    "end": context["recent"]["period_end"],
                    "days": context["recent"]["days"],
                }
                if context.get("recent")
                else None
            ),
        },
        "delta": context.get("delta"),
        "insight": insight,
        "cached": False,
    }
    _CACHE[key] = result
    return result


# ── 自由对话：店主自己提问 ──────────────────────────────────────

_CHAT_SYSTEM_PROMPT = """你是这家淘宝店铺的运营分析师，正在和店主对话。

你的输入里带了同一家店两个窗口的流量数据（见下方 JSON）：
长窗口是结构基线，短窗口是近期变化。两者嵌套，只能比日均和比率，
绝对不能相加、取平均或加权。

要求：
1. 只依据数据回答。数据里没有的信息（流量来源、竞品价格、成本、库存、
   评价内容、活动记录）直接说没有，不要推测。
2. 回答要短：一般 3 行以内，最多 5 行。先给结论，再给依据数字。
3. 提到具体商品时说明它属于哪个窗口，用「近 7 天」「近 30 天」这样的说法。
4. 用户问「该怎么办」时给可执行动作，不要写「加强优化」这类空话。
5. 不要输出 JSON，不要用 Markdown 表格。
"""

MAX_CHAT_TURNS = 8
MAX_MESSAGE_CHARS = 2000


def _clean_messages(messages: list[dict]) -> list[dict]:
    cleaned = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    return cleaned[-MAX_CHAT_TURNS:]


def chat(session: Session, *, store: int = 1, messages: list[dict]) -> dict:
    """带店铺数据上下文的自由问答。

    上下文每次请求现算（不缓存），保证店主导入新数据后立刻能问新问题。
    """
    context = build_context(session, store=store)
    if not context.get("available"):
        return {
            "available": False,
            "reason": context.get("reason", "no_data"),
            "reply": "还没有可用的流量数据，先在「数据导入 → 流量数据」上传生意参谋报表。",
        }

    cleaned = _clean_messages(messages)
    if not cleaned or cleaned[-1]["role"] != "user":
        return {"available": False, "reason": "no_question", "reply": ""}

    cfg = _config()
    if not is_configured():
        return {
            "available": True,
            "source": "rules",
            "reply": (
                "还没配置大模型，无法对话。在项目根目录 .env 填 "
                "AI_BASE_URL / AI_API_KEY / AI_MODEL 后重启后端即可。"
            ),
        }

    system = _CHAT_SYSTEM_PROMPT + "\n\n店铺数据：\n" + json.dumps(
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
            "reply": "模型调用失败（超时或网关异常），稍后再试一次。",
        }

    return {
        "available": True,
        "source": "llm",
        "model": cfg["model"],
        "reply": content.strip(),
    }
